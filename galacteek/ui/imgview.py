import functools

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QFile
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QCoreApplication

from PyQt5.QtGui import QImage
from PyQt5.QtGui import QMovie
from PyQt5.QtGui import QPixmap
from PyQt5.QtGui import QPalette
from PyQt5.QtGui import QKeySequence

from PyQt5.Qt import QSizePolicy

from PyQt5.QtWidgets import QFrame
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QScrollArea
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QSpacerItem
from PyQt5.QtWidgets import QLayout
from PyQt5.QtWidgets import QApplication

from galacteek import ensure
from galacteek import logUser
from galacteek.crypto.qrcode import IPFSQrDecoder
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.stat import StatInfo
from galacteek.ipfs.mimetype import MIMEType

from .widgets.pinwidgets import PinObjectButton

from .widgets import GalacteekTab
from .widgets import IPFSUrlLabel
from .widgets import IPFSPathClipboardButton
from .widgets import HashmarkThisButton
from .widgets import GMediumToolButton
from .helpers import getIcon
from .helpers import messageBox
from .clipboard import iCopyToClipboard
from .i18n import iZoomIn
from .i18n import iZoomOut
from .i18n import iOpen


def iImageGotQrCodes(count):
    return QCoreApplication.translate(
        'ImageView',
        'This image contains {} valid IPFS QR code(s) !').format(
            count)


def iImageCannotLoad(path):
    return QCoreApplication.translate(
        'ImageView',
        'Cannot load image {}').format(path)


class ImageViewerTab(GalacteekTab):
    def __init__(self, mainW):
        super().__init__(mainW)

        self.pinButton = PinObjectButton(parent=self)
        self.pinButton.setEnabled(True)

        self.zoomIn = GMediumToolButton(self)
        self.zoomIn.setIcon(getIcon('zoom-in.png'))
        self.zoomIn.setShortcut(QKeySequence('Ctrl++'))
        self.zoomIn.setToolTip(iZoomIn())
        self.zoomOut = GMediumToolButton(self)
        self.zoomOut.setIcon(getIcon('zoom-out.png'))
        self.zoomOut.setShortcut(QKeySequence('Ctrl+-'))
        self.zoomOut.setToolTip(iZoomOut())

        self.fitWindow = GMediumToolButton(self)
        self.fitWindow.setCheckable(True)
        self.fitWindow.setToolTip('Fit to window')
        self.fitWindow.setIcon(getIcon('expand.png'))

        self.pathLabel = IPFSUrlLabel(None)
        self.pathClipB = IPFSPathClipboardButton(None)
        self.hashmarkButton = HashmarkThisButton(IPFSPath(None))

        layout = QHBoxLayout()
        layout.addWidget(self.pathLabel, 0, Qt.AlignLeft)
        layout.addWidget(self.pathClipB, 0, Qt.AlignLeft)
        layout.addWidget(self.hashmarkButton, 0, Qt.AlignLeft)
        layout.addItem(
            QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        layout.addWidget(self.pinButton, 0, Qt.AlignLeft)
        layout.addItem(
            QSpacerItem(10, 10, QSizePolicy.Minimum, QSizePolicy.Minimum))
        layout.addWidget(self.zoomOut, 0, Qt.AlignLeft)
        layout.addWidget(self.zoomIn, 0, Qt.AlignLeft)
        layout.addWidget(self.fitWindow, 0, Qt.AlignLeft)

        self.vLayout.addLayout(layout)

        self.view = ImageView(self)
        self.view.imageLoaded.connect(self.onImageLoaded)
        self.view.qrCodesPresent.connect(self.onQrCodesListed)
        self.vLayout.addWidget(self.view)

        self.zoomIn.clicked.connect(self.view.zoomInClicked)
        self.zoomOut.clicked.connect(self.view.zoomOutClicked)
        self.fitWindow.clicked.connect(
            lambda: self.view.fitWindow(self.fitWindow.isChecked()))
        self.pinButton.clicked.connect(self.view.pinImage)

    def onImageLoaded(self, path, mimeType):
        self.hashmarkButton.ipfsPath = path
        self.pinButton.setEnabled(True)
        self.pinButton.changeObject(path)
        self.pathLabel.path = path
        self.pathClipB.path = path

    def onQrCodesListed(self, urls):
        # Create the scroll area and fix maximum height
        # TODO: set maximum size on resize as well
        scrollArea = QScrollArea()
        scrollArea.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        scrollArea.setWidgetResizable(True)
        scrollArea.setMaximumHeight(self.height() / 3)

        frame = QFrame(scrollArea)
        frame.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout()
        layout.setSizeConstraint(QLayout.SetMinAndMaxSize)

        scrollArea.setWidget(frame)

        iconOpen = getIcon('open.png')
        lbl = QLabel()
        lbl.setText(iImageGotQrCodes(len(urls)))
        lbl.setObjectName('qrCodeCountLabel')
        lbl.setStyleSheet('QLabel { font-size: 14pt; text-align: center; }')
        layout.addWidget(lbl)
        layout.addItem(
            QSpacerItem(10, 10, QSizePolicy.Minimum, QSizePolicy.Minimum))

        def onOpenItem(url):
            ensure(self.app.resourceOpener.open(url))

        for url in urls:
            hLayout = QHBoxLayout()
            hLayout.setSizeConstraint(QLayout.SetMinAndMaxSize)
            urlString = str(url)

            if len(urlString) > 92:
                urlText = urlString[0:92] + '...'
            else:
                urlText = urlString

            lbl = QLabel()
            lbl.setText('<b>{}</b>'.format(urlText))
            lbl.setToolTip(urlString)
            lbl.setStyleSheet('QLabel { font-size: 12pt }')

            clipBtn = GMediumToolButton(self)
            clipBtn.setIcon(getIcon('clipboard.png'))
            clipBtn.setToolTip(iCopyToClipboard())
            clipBtn.clicked.connect(
                functools.partial(self.app.setClipboardText, str(url)))

            openBtn = GMediumToolButton(self)
            openBtn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            openBtn.setIcon(iconOpen)
            openBtn.setText(iOpen())
            openBtn.clicked.connect(functools.partial(onOpenItem, url))

            hLayout.addWidget(lbl)
            hLayout.addWidget(openBtn)
            hLayout.addWidget(clipBtn)
            layout.addLayout(hLayout)

        frame.setLayout(layout)
        self.vLayout.addWidget(scrollArea)


class ImageView(QScrollArea):
    imageLoaded = pyqtSignal(IPFSPath, MIMEType)

    qrCodesPresent = pyqtSignal(list)

    def __init__(self, parent=None):
        super(ImageView, self).__init__(parent)

        self.app = QApplication.instance()
        self.image = QImage()

        self.clip = QMovie(self)
        self.clipFirstPixmap = None
        self.clipCurrentPixmap = None

        self.currentImgPath = None
        self.setObjectName('ImageView')

        self.qrDecoder = IPFSQrDecoder()
        self.labelImage = QLabel()
        self.setAlignment(Qt.AlignCenter)
        self.labelImage.setAlignment(Qt.AlignCenter)

        self.setBackgroundRole(QPalette.Dark)
        self.labelImage.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.labelImage.setScaledContents(True)
        self.scaleFactor = 1.0
        self.setWidget(self.labelImage)

    def wheelEvent(self, event):
        """
        Zoom in/out on the image on mouse wheel events
        """

        degrees = event.angleDelta()

        if degrees.y() == 0:
            return

        yDeg = max(min(60, abs(degrees.y())), 240)

        if degrees.y() > 0:
            factor = 1 + ((yDeg / 30) * 0.05)
            self.zoomIn(factor=factor)
        elif degrees.y() < 0:
            factor = 1 - ((yDeg / 30) * 0.05)
            self.zoomOut(factor=factor)

        event.accept()

    def pinImage(self):
        if self.currentImgPath and self.currentImgPath.valid:
            ensure(self.pinImageFromPath(self.currentImgPath))

    @ipfsOp
    async def pinImageFromPath(self, ipfsop, imgPath):
        await ipfsop.ctx.pin(str(imgPath))

    def fitWindow(self, fit):
        self.setWidgetResizable(fit)

        if not fit:
            self.scaleFactor = 1.0
            self.resizePixmap()

    def zoomOut(self, factor=0.75):
        self.scaleFactor *= factor
        self.resizePixmap()

    def zoomIn(self, factor=1.25):
        self.scaleFactor *= factor
        self.resizePixmap()

    def zoomInClicked(self):
        self.zoomIn()

    def zoomOutClicked(self):
        self.zoomOut()

    def resizePixmap(self):
        if self.labelImage.movie() and self.clipFirstPixmap:
            self.labelImage.resize(
                self.scaleFactor * self.clipFirstPixmap.size())
            return

        pixmap = self.labelImage.pixmap()

        if pixmap == 0 or pixmap is None:
            return

        self.labelImage.resize(
            self.scaleFactor * pixmap.size())

    @ipfsOp
    async def showImage(self, ipfsop, imgPath, fromBlock=False, timeout=10):
        try:
            if fromBlock is True:
                imgData = await ipfsop.waitFor(
                    ipfsop.client.block.get(imgPath), timeout
                )
            else:
                imgData = await ipfsop.waitFor(
                    ipfsop.catObject(imgPath), timeout
                )

            if not imgData:
                raise Exception('Failed to load image')

            mimeType, statInfo = await self.app.rscAnalyzer(
                IPFSPath(imgPath))

            if mimeType is None:
                raise Exception('Failed to load image')

            stat = StatInfo(statInfo)

            if mimeType.isAnimation:
                fp = self.app.tempDir.filePath(stat.cid)
                tmpFile = QFile(fp)

                if not tmpFile.exists() and tmpFile.open(QFile.ReadWrite):
                    tmpFile.write(imgData)
                    tmpFile.close()

                self.clip.stop()
                self.clip.setFileName(fp)
                self.labelImage.setMovie(self.clip)
                self.clip.frameChanged.connect(self.onMovieFrameChanged)
                self.clip.start()
                self.labelImage.adjustSize()
            else:
                img = QImage()
                img.loadFromData(imgData)
                self.image = img

                self.labelImage.setPixmap(QPixmap.fromImage(self.image))
                self.labelImage.adjustSize()
                self.resizePixmap()

                if self.qrDecoder:
                    # See if we have any QR codes in the image
                    urls = self.qrDecoder.decode(imgData)
                    if urls:
                        self.qrCodesPresent.emit(urls)

            self.labelImage.adjustSize()
            self.currentImgPath = IPFSPath(imgPath)
            self.imageLoaded.emit(self.currentImgPath, mimeType)

        except Exception:
            logUser.debug('Failed to load image: {path}'.format(
                path=imgPath))
            messageBox(iImageCannotLoad(imgPath))

    def onMovieFrameChanged(self, num):
        self.clipCurrentPixmap = self.clip.currentPixmap()

        if self.clipFirstPixmap is None:
            self.clipFirstPixmap = self.clipCurrentPixmap

    def onMovieError(self, err):
        logUser.info(
            f'{self.clip.fileName()}: {self.clip.lastErrorString()}')
