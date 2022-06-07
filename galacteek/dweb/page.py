from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebEngineWidgets import QWebEnginePage
from PyQt5.QtWebEngineWidgets import QWebEngineSettings
from PyQt5.QtWebChannel import QWebChannel

from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal
from PyQt5.QtCore import QJsonValue, QVariant, QUrl
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QColor

from PyQt5.QtWidgets import QApplication

from galacteek.ui.widgets import GalacteekTab
from galacteek.ui.helpers import questionBox
from galacteek import ensure
from galacteek import log
from galacteek.core import runningApp
from galacteek.dweb.render import renderTemplate
from galacteek.dweb.webscripts import ipfsClientScripts
from galacteek.dweb.webscripts import orbitScripts
from galacteek.browser.schemes import isIpfsUrl
from galacteek.ipfs.cidhelpers import IPFSPath


class BaseHandler(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)

    @pyqtSlot()
    def test(self):
        pass


class GalacteekHandler(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.app = QApplication.instance()

    @pyqtSlot(str)
    def openResource(self, path):
        if questionBox('Open resource',
                       f'Open object <b>{path}</b> ?'):
            ensure(self.app.resourceOpener.open(path))

    @pyqtSlot(str)
    def openIpfsLink(self, path):
        tab = self.app.mainWindow.addBrowserTab()
        tab.browseFsPath(path)

    @pyqtSlot(str)
    def copyToClipboard(self, path):
        if len(path) > 1024:
            return

        self.app.setClipboardText(path)

    @pyqtSlot(str)
    def explorePath(self, path):
        if len(path) > 1024:
            return

        self.app.mainWindow.explore(path)


class BasePage(QWebEnginePage):
    def __init__(self, template, url=None,
                 navBypassLinks=False,
                 openObjConfirm=True,
                 localCanAccessRemote=False,
                 webProfile=None,
                 parent=None):
        self.app = QApplication.instance()
        super(BasePage, self).__init__(
            webProfile if webProfile else self.app.webProfiles['ipfs'],
            parent)

        self.template = template
        self._handlers = {}
        self.pageCtx = {}
        self.channel = QWebChannel(self)
        self.url = url if url else QUrl('qrc:/')
        self.setUrl(self.url)
        self.setWebChannel(self.channel)
        self.webScripts = self.profile().scripts()
        self.navBypass = navBypassLinks
        self.openObjConfirm = openObjConfirm
        self.localCanAccessRemote = localCanAccessRemote

        self.settings().setAttribute(
            QWebEngineSettings.LocalStorageEnabled,
            True)
        self.settings().setAttribute(
            QWebEngineSettings.LocalContentCanAccessFileUrls,
            True)

        self.featurePermissionRequested.connect(self.onPermissionRequest)
        self.fullScreenRequested.connect(self.onFullScreenRequest)

        self.installScripts()
        self.setPermissions()
        ensure(self.render())

    def onPermissionRequest(self, url, feature):
        pass

    def onFullScreenRequest(self, req):
        req.reject()

    def installScripts(self):
        pass

    def setPermissions(self):
        if self.localCanAccessRemote:
            self.settings().setAttribute(
                QWebEngineSettings.LocalContentCanAccessRemoteUrls,
                True
            )

        self.settings().setAttribute(
            QWebEngineSettings.FullScreenSupportEnabled,
            True
        )

    def register(self, name, obj):
        self.channel.registerObject(name, obj)
        self._handlers[name] = obj

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceId):
        log.debug(
            'JS: level: {0}, source: {1}, line: {2}, message: {3}'.format(
                level,
                sourceId,
                lineNumber,
                message))

    async def render(self):
        if self.template:
            self.setHtml(await renderTemplate(self.template, **self.pageCtx),
                         baseUrl=self.url)

    def acceptNavigationRequest(self, url, navType, isMainFrame):
        if self.navBypass and \
                navType == QWebEnginePage.NavigationTypeLinkClicked:
            if isIpfsUrl(url):
                path = IPFSPath(url.toString(), autoCidConv=True)
                if path.valid:
                    if self.openObjConfirm:
                        if questionBox('Open resource',
                                       f'Open object <b>{path}</b> ?'):
                            ensure(self.app.resourceOpener.open(path))
                    else:
                        ensure(self.app.resourceOpener.open(path))

                    return False

            elif url.scheme() in ['http', 'https', 'ftp', 'manual']:
                tab = self.app.mainWindow.addBrowserTab()
                tab.enterUrl(url)
                return False

        return True


class IPFSPage(BasePage):
    def installScripts(self):
        exSc = self.webScripts.findScript('ipfs-http-client')
        if exSc.isNull():
            scripts = self.app.scriptsIpfs
            [self.webScripts.insert(script) for script in scripts]


class OrbitPage(BasePage):
    def installScripts(self):
        exSc = self.webScripts.findScript('ipfs-http-client')
        if exSc.isNull():
            log.debug('Adding ipfs-http-client scripts')

            scripts = ipfsClientScripts(self.app.getIpfsConnectionParams())
            for script in scripts:
                self.webScripts.insert(script)

        exSc = self.webScripts.findScript('orbit-db')
        if exSc.isNull():
            log.debug('Adding orbit-db scripts')
            scripts = orbitScripts(self.app.getIpfsConnectionParams())
            for script in scripts:
                self.webScripts.insert(script)


class HashmarksHandler(BaseHandler):
    marksListed = pyqtSignal(str, QJsonValue)

    def __init__(self, marksLocal, marksShared, parent=None):
        super(HashmarksHandler, self).__init__(parent)
        self.marksLocal = marksLocal
        self.marksShared = marksShared

    @pyqtSlot(str, result=list)
    def categories(self, ns):
        if ns == 'local':
            return self.marksLocal.getCategories()
        else:
            return self.marksShared.getCategories()

    @pyqtSlot(str, str, result=QJsonValue)
    def marks(self, cat, ns):
        source = self.marksLocal if ns == 'local' else self.marksShared
        marks = source.getCategoryMarks(cat)
        return QJsonValue.fromVariant(QVariant(marks))

    @pyqtSlot(str)
    def deleteHashmark(self, path):
        self.marksLocal.delete(path)


class HashmarksPage(IPFSPage):
    def __init__(self, marksLocal, marksNetwork, parent=None):
        super(HashmarksPage, self).__init__('hashmarks.html', parent=parent)

        self.marksLocal = marksLocal
        self.marksNetwork = marksNetwork
        self.marksLocal.markAdded.connect(
            lambda path, mark: self.onMarksChanged())
        self.marksLocal.feedMarkAdded.connect(
            lambda path, mark: self.onMarksChanged())

        self.hashmarks = HashmarksHandler(self.marksLocal,
                                          self.marksNetwork, self)
        self.register('hashmarks', self.hashmarks)
        self.register('galacteek', GalacteekHandler(None))

        self.timerRerender = QTimer()

    def onMarksChanged(self):
        ensure(self.render())

    def onSharedMarksChanged(self):
        if self.timerRerender.isActive():
            self.timerRerender.stop()
        self.timerRerender.start(2000)

    async def render(self):
        self.setHtml(await renderTemplate(
            self.template,
            ipfsConnParams=self.app.getIpfsConnectionParams(),
            marks=self.marksLocal,
            marksShared=self.marksNetwork),
            baseUrl=QUrl('qrc:/'))


class PDFViewerHandler(BaseHandler):
    marksListed = pyqtSignal(str, QJsonValue)

    def __init__(self, ipfsPath, parent=None):
        super(PDFViewerHandler, self).__init__(parent)
        self.ipfsPath = ipfsPath

    @pyqtSlot(result=str)
    def getPdfPath(self):
        return self.ipfsPath


class PDFViewerPage(IPFSPage):
    def __init__(self, ipfsPath, parent=None):
        super(PDFViewerPage, self).__init__('pdfviewer.html', parent=parent)
        self.ipfsPath = ipfsPath
        self.register('galacteek', GalacteekHandler(None))
        self.register('pdfview', PDFViewerHandler(self.ipfsPath))


class DWebView(QWebEngineView):
    """
    TODO: deprecate asap
    """

    def __init__(self, page=None, parent=None):
        super(DWebView, self).__init__(parent)
        self.app = runningApp()
        self.channel = QWebChannel()
        self.p = page
        self.show()

        self.webSettings = self.settings()
        self.webSettings.setAttribute(QWebEngineSettings.LocalStorageEnabled,
                                      True)

    @property
    def p(self):
        return self._currentPage

    @p.setter
    def p(self, page):
        if page:
            self._currentPage = page
            self.setPage(page)
            self.page().setBackgroundColor(
                QColor(self.app.theme.colors.webEngineBackground))


class WebTab(GalacteekTab):
    def __init__(self, mainW):
        super(WebTab, self).__init__(mainW)

    def attach(self, view):
        self.vLayout.addWidget(view)
