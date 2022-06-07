import asyncio
import aiorwlock
from cachetools import TTLCache

from async_generator import async_generator, yield_, yield_from_

from PyQt5.QtCore import (pyqtSignal, QObject)

from galacteek import log
from galacteek import ensure
from galacteek import AsyncSignal
from galacteek.ipfs.paths import posixIpfsPath
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.cidhelpers import joinIpfs
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.ipfsops import *  # noqa
from galacteek.ipfs import pb
from galacteek.core.asynclib import async_enterable
from galacteek.core.jtraverse import traverseParser
from galacteek.core import utcDatetimeIso

from galacteek.core.asynccache import selfcachedcoromethod


class DAGObj:
    def __init__(self, data):
        self.data = data


class DAGRewindException(Exception):
    pass


class DAGError(Exception):
    pass


class DAGEditor(object):
    def __init__(self, dag):
        self.dag = dag

    @property
    def d(self):
        return self.dag.d

    async def __aenter__(self):
        log.debug('Editing DAG: {cid}'.format(cid=self.dag.dagCid))
        return self

    async def __aexit__(self, *args):
        await self.dag.sync()


class DeadEnd(object):
    def __init__(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class DAGOperations:
    def debug(self, msg):
        log.debug(msg)

    @ipfsOp
    async def get(self, op, path):
        self.debug('DAG get: {}'.format(posixIpfsPath.join(self.dagCid, path)))
        try:
            dagNode = await op.dagGet(
                posixIpfsPath.join(self.dagCid, path))
        except aioipfs.APIError as err:
            log.debug('DAG get: {0}. An error occured: {1}'.format(
                path, err.message))
            return None

        if isinstance(dagNode, dict) and 'data' in dagNode and \
                'links' in dagNode:
            """ Try and decode the protobuf data """
            msg = pb.decodeUnixfsDagNode(dagNode['data'])
            if not msg:
                return
            return msg['data']
        else:
            return dagNode

    @ipfsOp
    async def cat(self, op, path):
        try:
            return await op.client.cat(
                posixIpfsPath.join(self.dagCid, path))
        except aioipfs.APIError as err:
            self.debug(f'Cat error ({path}): {err.message}')
            return None

    @ipfsOp
    async def list(self, op, path=''):
        data = await self.get(path)
        if data is None:
            return

        if isinstance(data, dict):
            return list(data.keys())

    @ipfsOp
    async def chNode(self, ipfsop, path, start=None, create=False):
        comps = path.split('/')
        cur = start if start else self.dagRoot

        for comp in comps:
            if comp not in cur:
                if create:
                    cur[comp] = {}
                    cur = cur[comp]
                else:
                    return cur
            else:
                cur = cur[comp]

        return cur

    @ipfsOp
    async def resolve(self, op, path=''):
        return await op.resolve(
            posixIpfsPath.join(self.dagCid, path), recursive=True)

    @async_generator
    async def walk(self, op, path='', maxObjSize=0, depth=1):
        """
        Do not use this!
        """

        data = await self.get(path)
        if data is None:
            return

        if isinstance(data, dict) and 'data' in data and 'links' in data:
            """ Try and decode the protobuf data """
            msg = pb.decodeUnixfsDagNode(data['data'])
            if not msg:
                return
            if maxObjSize == 0 or \
                    (maxObjSize > 0 and msg['size'] < maxObjSize):
                await yield_((path, DAGObj(msg['data'])))

        if not data:
            return

        if isinstance(data, dict):
            for objKey, objValue in data.items():
                if objKey == '/':
                    out = await op.client.cat(objValue)
                    await yield_((path, DAGObj(out)))
                if objKey == 'data' or objKey == 'links':
                    continue
                else:
                    await yield_from_(
                        self.walk(op, path=posixIpfsPath.join(path, objKey),
                                  maxObjSize=maxObjSize, depth=depth)
                    )

        elif isinstance(data, list):
            for idx, obj in enumerate(data):
                await yield_from_(
                    self.walk(op, path=posixIpfsPath.join(path, str(idx)),
                              maxObjSize=maxObjSize)
                )
        elif isinstance(data, str):
            await yield_((path, DAGObj(data)))

    def mkLink(self, cid):
        if isinstance(cid, str):
            return {"/": cid}
        elif isinstance(cid, dict) and 'Hash' in cid:
            return {"/": cid['Hash']}

    @ipfsOp
    async def inline(self, ipfsop):
        # In-line the JSON-LD contexts in the DAG for JSON-LD usage

        return await ipfsop.ldInline(await self.get())

    @ipfsOp
    async def expand(self, ipfsop):
        """
        Perform a JSON-LD expansion
        """

        try:
            async with ipfsop.ldOps() as ld:
                return await ld.expandDocument(await self.get(path=''))
        except Exception as err:
            self.debug('Error expanding document: {}'.format(
                str(err)))

    async def __aexit__(self, *args):
        pass

    ipld = mkLink


class DAGPortal(QObject, DAGOperations):
    """
    DAG portal
    """

    cidChanged = pyqtSignal(str)
    loaded = pyqtSignal(str)

    def __init__(self, dagCid=None, dagRoot=None, offline=False,
                 parent=None, lock=None, timeoutLoad=10):
        super().__init__(parent)
        self._dagCid = dagCid
        self._dagRoot = dagRoot
        self._dagPath = IPFSPath(self._dagCid)
        self.lock = lock if lock else asyncio.Lock()
        self.evLoaded = asyncio.Event()
        self.offline = offline
        self.timeoutLoad = timeoutLoad

    @property
    def d(self):
        return self._dagRoot

    @property
    def root(self):
        return self._dagRoot

    def debug(self, msg):
        log.debug('DAGPortal({cid}): {msg}'.format(
            cid=self.dagCid, msg=msg))

    @property
    def dagCid(self):
        return self._dagCid

    @dagCid.setter
    def dagCid(self, val):
        self._dagCid = val
        self._dagPath = IPFSPath(self._dagCid)
        self.cidChanged.emit(val)

    @property
    def dagPath(self):
        return self._dagPath

    @property
    def dagRoot(self):
        return self._dagRoot

    def path(self, subpath):
        return posixIpfsPath.join(joinIpfs(self.dagCid), subpath)

    def child(self, subpath):
        if self.dagPath.valid:
            return self.dagPath.child(subpath)

    async def waitLoaded(self, timeout=15):
        return asyncio.wait_for(self.evLoaded.wait(), timeout)

    @ipfsOp
    async def load(self, op, timeout=None):
        self._dagRoot = await op.waitFor(
            op.dagGet(self.dagCid),
            timeout if timeout else self.timeoutLoad
        )

        if self.dagRoot:
            self.evLoaded.set()
            self.loaded.emit(self.dagCid)
            return self.dagRoot

    @ipfsOp
    async def sync(self, op, timeout=10):
        try:
            cid = await op.waitFor(
                op.dagPut(self.dagRoot, offline=self.offline), timeout)
        except aioipfs.APIError as err:
            self.debug(f'Sync error: {err.message}')
        else:
            self.dagCid = cid

    async def __aenter__(self):
        await self.lock.acquire()

        if self.dagRoot is None:
            await self.load()
            if self.dagRoot is None:
                raise DAGError('Cannot load dag')

        return self

    @async_enterable
    async def edit(self):
        return DAGEditor(self)

    async def __aexit__(self, *args):
        self.lock.release()

    def link(self, cid):
        if isinstance(cid, str):
            return {"/": cid}
        elif isinstance(cid, dict) and 'Hash' in cid:
            return {"/": cid['Hash']}


class EvolvingDAG(QObject, DAGOperations):
    """
    Evolving (mutating) DAG protected by a RW-lock

    :param str dagMetaMfsPath: the path inside the MFS for the metadata
        describing this DAG
    """

    changed = pyqtSignal()
    dagCidChanged = pyqtSignal(str)
    metadataEntryChanged = pyqtSignal()

    keyCidLatest = 'cidlatest'

    def __init__(self, dagMetaMfsPath, dagMetaHistoryMax=12, offline=False,
                 unpinOnUpdate=False, autoPreviousNode=True,
                 cipheredMeta=False,
                 autoUpdateDates=False, loop=None,
                 portalCacheTtl=60):
        super().__init__()

        self.loop = loop if loop else asyncio.get_event_loop()
        self.lock = aiorwlock.RWLock(loop=loop)
        self.loaded = asyncio.Future()
        self.portalCache = TTLCache(1, portalCacheTtl)

        self._curMetaEntry = None
        self._dagRoot = None
        self._dagMeta = None
        self._dagCid = None
        self._offline = offline
        self._dagMetaMaxHistoryItems = dagMetaHistoryMax
        self._dagMetaMfsPath = dagMetaMfsPath
        self._unpinOnUpdate = unpinOnUpdate
        self._autoPrevious = autoPreviousNode
        self._autoUpdateDates = autoUpdateDates
        self._cipheredMeta = cipheredMeta

        self.dagUpdated = AsyncSignal(str)
        self.available = AsyncSignal(object)

        self.changed.connect(lambda: ensure(self.ipfsSave()))

    @property
    def wLock(self):
        return self.lock.writer_lock

    @property
    def rLock(self):
        return self.lock.reader_lock

    @property
    def dagMetaMfsPath(self):
        return self._dagMetaMfsPath  # path inside the mfs

    @property
    def dagMetaMaxHistoryItems(self):
        return self._dagMetaMaxHistoryItems

    @property
    def curMetaEntry(self):
        return self._curMetaEntry

    @curMetaEntry.setter
    def curMetaEntry(self, value):
        self._curMetaEntry = value

    @property
    def dagCid(self):
        return self._dagCid

    @dagCid.setter
    def dagCid(self, cid):
        self._dagMeta[self.keyCidLatest] = cid
        self._dagCid = cid
        self.debug("DAG's CID now is {0}".format(cid))
        self.dagCidChanged.emit(cid)

    @property
    def dagMeta(self):
        return self._dagMeta

    @property
    def dagRoot(self):
        return self._dagRoot

    @property
    def root(self):
        return self._dagRoot

    def debug(self, msg):
        log.debug('EDAG ({meta}): {msg}'.format(
            meta=self.dagMetaMfsPath, msg=msg))

    async def initDag(self, ipfsop):
        return {}

    def updateDagSchema(self, dag):
        pass

    async def load(self):
        await self.loadDag()

    @ipfsOp
    async def loadDag(self, op):
        self.debug('Loading DAG metadata file')

        if self._cipheredMeta:
            meta = await op.rsaAgent.decryptMfsJson(self.dagMetaMfsPath)
        else:
            meta = await op.filesReadJsonObject(self.dagMetaMfsPath)
            self.debug('Metadata is {}'.format(meta))

        if meta is not None:
            self._dagMeta = meta
            latest = self.dagMeta.get(self.keyCidLatest, None)
            if latest:
                self.dagCid = latest
                self.debug('Getting DAG: {cid}'.format(cid=self.dagCid))
                self._dagRoot = await op.dagGet(self.dagCid)

                if self.dagRoot:
                    if self.updateDagSchema(self.dagRoot) is True:
                        # save right away
                        await self.ipfsSave()
            else:
                self.debug('No CID history, reinitializing')
                # How inconvenient ..
                # TODO: the history could be used here to recreate a DAG
                # from previous CIDs but we really shouldn't have to enter here
                self._dagRoot = {}

            self.loaded.set_result(True)
        else:
            self._dagMeta = {
                self.keyCidLatest: None,
                'history': []
            }
            self._dagRoot = await self.initDag(op)
            self.updateDagSchema(self.dagRoot)
            await self.ipfsSave()
            self.loaded.set_result(True)

        self.parser = traverseParser(self.dagRoot)
        await self.available.emit(self.dagRoot)

    @ipfsOp
    async def ipfsSave(self, op):
        self.debug('Saving (acquiring lock)')

        async with self.wLock:
            prevCid = self.dagCid
            history = self.dagMeta.setdefault('history', [])
            maxItems = self.dagMetaMaxHistoryItems

            if prevCid and self._autoPrevious:
                # Create a 'previous' IPLD link
                self.dagRoot['previous'] = self.mkLink(prevCid)

            if isinstance(self.dagRoot, dict) and self._autoUpdateDates:
                # Update 'datemodified' if enabled
                if 'datemodified' in self.dagRoot:
                    self.dagRoot['datemodified'] = utcDatetimeIso()

            # We always PIN the latest DAG and do a pin update using the
            # previous item in the history

            cid = await op.dagPut(self.dagRoot, pin=True,
                                  offline=self._offline)
            if cid is not None:
                if prevCid is not None and prevCid not in history:
                    if len(history) > maxItems:
                        # Purge old items
                        [history.pop() for idx in range(
                            0, len(history) - maxItems)]

                    history.insert(0, prevCid)

                    if 0:
                        # pinUpdate randomly blocks so
                        # disable it for now
                        await op.pinUpdate(
                            prevCid, cid, unpin=self._unpinOnUpdate)

                # Save the new CID and update the metadata
                await self.saveNewCid(cid)
            else:
                # Bummer
                self.debug('DAG could not be built')
                return False

        self.debug('Saved (wlock released)')
        return True

    @ipfsOp
    async def saveNewCid(self, ipfsop, cid):
        # Save the new CID and update the metadata
        self.dagCid = cid

        if self._cipheredMeta:
            await ipfsop.rsaAgent.encryptJsonToMfs(
                self.dagMeta,
                self.dagMetaMfsPath
            )

        else:
            await ipfsop.filesWriteJsonObject(self.dagMetaMfsPath,
                                              self.dagMeta)
        entry = await ipfsop.filesStat(self.dagMetaMfsPath)
        if entry:
            self.curMetaEntry = entry

        await self.dagUpdated.emit(cid)

    @ipfsOp
    async def rewind(self, ipfsop):
        """
        Using the history, rewind the EDAG in time
        (the first CID in the history becomes the new CID)

        Since we're using pinUpdate() when upgrading
        the DAG, we check that the object corresponding
        to the "previous" CID in the history is still available
        (didn't get collected) before rewriting the history.
        """

        history = self.dagMeta['history']
        prevCid = self.dagMeta[self.keyCidLatest]

        async with self.wLock:
            if len(history) >= 2:
                newCid = history[0]

                # Load the DAG corresponding to the previous CID
                # Timeout is lower than the default, we can't hold
                # the lock for too long
                pDag = await ipfsop.dagGet(newCid, timeout=5)

                if not pDag:
                    # We don't have it :\
                    raise DAGRewindException(
                        'Previous object unavailable')

                # Pop it now and set the latest CID
                history.pop(0)
                self.dagMeta[self.keyCidLatest] = newCid

                # Save metadata, and save this DAG, replacing dagRoot
                # Do the pin update
                self._dagRoot = pDag
                await self.saveNewCid(newCid)

                await ipfsop.waitFor(
                    ipfsop.pinUpdate(prevCid, newCid,
                                     unpin=self._unpinOnUpdate),
                    10
                )
            else:
                raise DAGRewindException('No DAG history')

    async def __aenter__(self):
        """
        Write lock is acquired on entering the async ctx manager
        """
        await self.wLock.acquire()
        return self

    async def __aexit__(self, *args):
        """
        Release the write lock and save. The changed signal is emitted
        """
        self.wLock.release()
        self.changed.emit()

    @async_enterable
    @selfcachedcoromethod('readCache')
    async def read(self):
        """
        Return a read-only portal, its context manager uses the read lock
        """
        return DAGPortal(dagCid=self.dagCid, dagRoot=self.dagRoot,
                         lock=self.rLock)

    @async_enterable
    @selfcachedcoromethod('portalCache')
    async def portalToPath(self, path, dagClass=DAGPortal):
        resolved = await self.resolve(path=path)
        if resolved:
            return dagClass(dagCid=resolved)
        else:
            raise DAGError(f'Cannot find {path} in DAG {self.dagCid}')

    @async_enterable
    async def portal(self):
        return DAGPortal(dagCid=self.dagCid, dagRoot=self.dagRoot)
