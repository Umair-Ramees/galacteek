import asyncio
import io
import functools
import platform
import re

from urllib.parse import parse_qs

from ctypes import cdll
from ctypes.util import find_library

import qrcode
from PIL.Image import new as NewImage
from PIL import Image

from galacteek import log
from galacteek.core.tmpf import TmpFile
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs import ipfsOp
from galacteek.did import didRe


def zbar_load():
    # Like zbar.zbar_library.load() but uses 'libzbar.so.0'
    # if find_library() returns nothing, so that we can use
    # the libzbar from the AppImage

    path = find_library('zbar')
    pl = platform.system()

    if not path:
        if pl == 'Linux' or pl.endswith('BSD'):
            path = 'libzbar.so.0'
        elif pl == 'Darwin':
            path = 'libzbar.0.dylib'
        elif pl == 'Windows':
            path = 'libzbar-64.dll'

    log.debug('Loading zbar library from: {}'.format(path))

    try:
        libzbar = cdll.LoadLibrary(path)
    except Exception as err:
        log.debug(f'Could not load zbar lib from: {path}: {err}')
        return None, []
    else:
        log.debug('Loaded zbar lib from: {}'.format(path))
        return libzbar, []


try:
    from pyzbar import zbar_library

    if platform.system() != 'Windows':
        zbar_library.load = zbar_load

    from pyzbar.pyzbar import decode as zbar_decode
except Exception:
    import traceback
    traceback.print_exc()
    haveZbar = False
else:
    haveZbar = True


try:
    from qreader.decoder import QRDecoder
    from qreader.scanner import ImageScanner
except ImportError:
    haveQReader = False
else:
    haveQReader = True


class ImageReader:
    def _getImage(self, data):
        try:
            image = Image.open(io.BytesIO(data))
        except:
            log.debug('Cannot open image with Pillow')
            return None
        else:
            return image


class ZbarCryptoCurrencyQrDecoder(ImageReader):
    """
    Decodes Crypto QR codes with the zbar library
    """

    def decode(self, data):
        """
        :param bytes data: Raw image data or Pillow image
        :rtype: list
        """

        if isinstance(data, bytes):
            image = self._getImage(data)
        elif isinstance(data, Image.Image):
            image = data
        else:
            raise Exception('Need bytes or PIL.Image')

        if image is None:
            return None

        try:
            objects = zbar_decode(image)

            addrs = []
            for obj in objects:
                if not isinstance(obj.data, bytes):
                    continue

                try:
                    decoded = obj.data.decode()
                except BaseException as err:
                    log.debug(f'pyzbar decode: error decoding item: {err}')
                    continue

                # BTC
                ma = re.match(
                    r'^bitcoin:(?P<addr>[\w]{27,42})\??(?P<qs>[\w\=\.\?]*)?',
                    decoded
                )
                if ma:
                    gd = ma.groupdict()
                    query = parse_qs(gd.get('qs'))

                    amountl = query.get('amount') if query else None
                    try:
                        amount = float(amountl.pop())
                    except Exception:
                        amount = None

                    addrs.append({
                        'currency': 'BTC',
                        'address': gd.get('addr'),
                        'amount': amount
                    })

            if len(addrs) > 0:  # don't return empty list
                return addrs
        except Exception as err:
            log.debug(f'pyzbar decode error: {err}')
            return None


class ZbarIPFSQrDecoder(ImageReader):
    """
    Decodes IPFS QR codes with the zbar library
    """

    def decode(self, data):
        """
        :param bytes data: Raw image data or Pillow image
        :rtype: list
        """

        if isinstance(data, bytes):
            image = self._getImage(data)
        elif isinstance(data, Image.Image):
            image = data
        else:
            raise Exception('Need bytes or PIL.Image')

        if image is None:
            return None

        try:
            objects = zbar_decode(image)

            urls = []
            for obj in objects:
                if not isinstance(obj.data, bytes):
                    log.debug('pyzbar decode: invalid type')
                    continue

                try:
                    decoded = obj.data.decode()
                except BaseException as err:
                    log.debug(f'pyzbar decode: error decoding item: {err}')
                    continue

                if len(decoded) not in range(1, 1024):
                    log.debug('pyzbar decode: decoded value not in range')
                    continue

                path = IPFSPath(decoded, autoCidConv=True)
                if path.valid and path not in urls:
                    log.debug('Decoded IPFS QR: {}'.format(path))
                    urls.append(path)
                elif didRe.match(decoded):
                    log.debug('Decoded DID QR: {}'.format(decoded))
                    urls.append(decoded)

            if len(urls) > 0:  # don't return empty list
                return urls
        except Exception as err:
            log.debug(f'pyzbar decode error: {err}')
            return None


class QReaderIPFSQrDecoder(ImageReader):
    """
    Decodes IPFS QR codes with the qreader library
    """

    def decode(self, data):
        """
        Try to decode all the QR codes with IPFS addresses contained
        in an image. Returns a list of IPFS paths, or None if no URL
        was found.

        :param bytes data: Raw image data or Pillow image
        :rtype: list
        """

        if isinstance(data, bytes):
            image = self._getImage(data)
        elif isinstance(data, Image):
            image = data
        else:
            raise Exception('Need bytes or PIL.Image')

        if image is None:
            return

        try:
            imgScanner = ImageScanner(image)
            results = QRDecoder(imgScanner).get_all()

            urls = []
            for obj in results:
                if not isinstance(obj, str):
                    continue
                if len(obj) not in range(1, 1024):
                    continue

                path = IPFSPath(obj)
                if path.valid and path not in urls:
                    urls.append(path)

            if len(urls) > 0:  # don't return empty list
                return urls
        except Exception:
            return None


class IPFSQrEncoder:
    def __init__(self, maxCodes=100):
        self._codes = []
        self._maxCodes = maxCodes

    @property
    def codes(self):
        return self._codes

    def add(self, url: str):
        if url and len(self._codes) < self._maxCodes:
            self._codes.append(url)

    def _newImage(self, width, height, mode='P', fill=255, color='#000000'):
        """ Create a new Pillow image with the given params """
        img = NewImage(mode, (width, height), color=color)
        img.paste(fill, (0, 0, img.width, img.height))
        return img

    def _newQrCode(self, qrVersion=1, border=2, boxsize=10, **custom):
        """ Create a new QR code with the given params """
        return qrcode.QRCode(
            version=qrVersion,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=boxsize,
            border=border,
            **custom
        )

    def encodeUrl(self, url, fillColor='black', backColor='white',
                  qrVersion=1):
        """ Encode an URL and return a PIL image """
        qr = self._newQrCode(qrVersion=qrVersion)
        qr.add_data(url)
        qr.make()

        qrImage = qr.make_image(fill_color=fillColor, back_color=backColor)
        return qrImage.get_image()

    @ipfsOp
    async def encodeAndStore(self, ipfsop, loop=None, executor=None,
                             filename=None, format='raw', **kw):
        try:
            entry = None
            img = await self.encodeAll(loop=loop, executor=executor, **kw)

            if not img:
                raise Exception('Could not encode QR')

            if format == 'raw':
                return await ipfsop.addBytes(img.tobytes())
            elif format == 'png':
                with TmpFile(suffix='.png') as tfile:
                    img.save(tfile.name)
                    entry = await ipfsop.addPath(tfile.name)

                return entry
        except Exception as e:
            log.debug('Error encoding/storing QR code: {}'.format(str(e)))

    async def encodeAll(self, loop=None, executor=None, method='append',
                        version=12):
        """
        Runs the encoding in an asyncio executor
        """
        loop = loop if loop else asyncio.get_event_loop()
        return await loop.run_in_executor(
            executor,
            functools.partial(self._encodeAllAppend, version=version))

    def _encodeAllAppend(self, version=12):
        """
        Generate all the QR codes and embed them all into one image by
        appending. We use QR version 12 by default

        Does basically something similar to what 'convert +append' would do,
        but probably less elegantly.

        :return: an image containing all the QR codes
        :rtype: PIL.Image
        """

        baseImageWidth = 0
        baseImageHeight = 0

        # Base image sizes based on the QR count
        # The image is resized in height if needed to fit more codes

        unit = 172
        imageSizes = {
            range(1, 20): (unit * 4, unit * 4),
            range(20, 50): (unit * 6, unit * 6),
            range(50, 70): (unit * 6, unit * 8),
            range(70, 101): (unit * 8, unit * 8)
        }

        for _range, size in imageSizes.items():
            if len(self.codes) in _range:
                baseImageWidth, baseImageHeight = size
                break

        if baseImageWidth == 0 or baseImageHeight == 0:
            raise ValueError('Cannot generate image with these parameters')

        imgMosaic = self._newImage(baseImageWidth, baseImageHeight)

        lastImage = None
        posX = 0
        posY = 0
        highest = 0

        for count, url in enumerate(self.codes):
            if len(str(url)) > 1024:
                log.debug('QR#{count} ({url}): too large, ignoring'.format(
                    count=count, url=url))
                continue

            img = self.encodeUrl(url, qrVersion=version)

            if not img:
                log.debug('QR#{count} ({url}): empty image?'.format(
                    count=count, url=url))
                continue

            try:
                # Why not ?
                img = img.resize((int(img.width / 4), int(img.height / 4)))
            except:
                log.debug('QR#{count} ({url}): cannot resize image'.format(
                    count=count, url=url))
                continue

            if img.height > highest:
                highest = img.height

            if posX + img.width > imgMosaic.width:
                # Sort of a carriage return
                posY += highest
                posX = 0
                highest = 0

            if posY + img.height > imgMosaic.height:
                imgNew = self._newImage(imgMosaic.width, posY + img.height)
                imgNew.paste(imgMosaic, (0, 0))
                imgMosaic = imgNew

            log.debug('QR #{count} (size: {size}) at: {posx}:{posy}'.format(
                count=count + 1, posx=posX, posy=posY, size=len(url)))

            imgPosY = posY
            if highest > img.height:
                imgPosY = posY + int((highest - img.height) / 2)

            imgMosaic.paste(
                img, (posX, imgPosY, posX + img.width, imgPosY + img.height))

            posX += img.width
            lastImage = img

        if lastImage is not None:
            # Crop it

            imgMosaic = imgMosaic.crop(
                (0, 0, posX if posY == 0 else imgMosaic.width,
                    posY + lastImage.height)
            )

        return imgMosaic


class CCQrEncoder:
    def _newQrCode(self, qrVersion=1, border=0, boxsize=16, **custom):
        return qrcode.QRCode(
            version=qrVersion,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=boxsize,
            border=border,

            **custom
        )

    def encodeUri(self, url, fillColor='black', backColor='white',
                  qrVersion=1, size=None):
        """ Encode an URL and return a PIL image """
        qr = self._newQrCode(qrVersion=qrVersion)
        qr.add_data(url)
        qr.make()

        qrImage = qr.make_image(fill_color=fillColor, back_color=backColor)
        img = qrImage.get_image()

        if size:
            return img.resize(size)

        return img

    async def encode(self, url,
                     loop=None, executor=None,
                     version=1,
                     size=(256, 256)):
        """
        Runs the encoding in an asyncio executor
        """
        loop = loop if loop else asyncio.get_event_loop()
        return await loop.run_in_executor(
            executor,
            functools.partial(self.encodeUri, url, qrVersion=version,
                              size=size))


def IPFSQrDecoder():
    # Returns a suitable QR decoder depending on the available libs
    if haveZbar:
        log.debug('Using pyzbar decoder')
        return ZbarIPFSQrDecoder()
    elif haveQReader:
        log.debug('Using qreader decoder')
        return QReaderIPFSQrDecoder()
    else:
        log.debug('No QR decoder available')
        return None
