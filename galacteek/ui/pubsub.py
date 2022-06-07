import functools
import json

from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QTextBrowser

from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtWidgets import QTableWidget
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QHeaderView
from PyQt5.QtWidgets import QToolButton

from PyQt5.QtGui import QTextCursor
from PyQt5.QtGui import QFont
from PyQt5.QtGui import QBrush
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt

from galacteek import log

from galacteek.core import datetimeIsoH

from galacteek.core.ps import keyPsJson
from galacteek.core.ps import keyPsEncJson
from galacteek.core.ps import psSubscriber

from galacteek.ipfs.pubsub import TOPIC_CHAT
from galacteek.ipfs.pubsub import TOPIC_PEERS
from galacteek.ipfs.pubsub import TOPIC_LD_PRONTO

from .helpers import getIcon
from .widgets import GalacteekTab


class PubsubSnifferWidget(GalacteekTab):
    def __init__(self, gWindow):
        super(PubsubSnifferWidget, self).__init__(gWindow)

        self.subscriber = psSubscriber('pubsub_sniffer')

        self.tableWidget = QTableWidget(self)
        self.tableWidget.setHorizontalHeaderLabels(
            ['Date', 'Topic', 'Sender', ''])
        self.tableWidget.setColumnCount(4)
        self.tableWidget.verticalHeader().hide()
        self.tableWidget.horizontalHeader().hide()

        horizHeader = self.tableWidget.horizontalHeader()
        horizHeader.setSectionResizeMode(QHeaderView.ResizeToContents)
        self.vLayout.addWidget(self.tableWidget)

        self.subscriber.add_async_listener(keyPsJson, self.onJsonMessage)
        self.subscriber.add_async_listener(keyPsEncJson, self.onJsonMessage)

    async def onJsonMessage(self, key, message):
        try:
            await self.processMessage(key, message)
        except Exception as err:
            log.warning(f'Unable to process pubsub message: {err}')

    async def processMessage(self, key, message):
        sender, topic, jsonMsg = message

        dItem = QTableWidgetItem(datetimeIsoH())

        maxLen = 24
        if len(topic) > maxLen:
            tItem = QTableWidgetItem(topic[0:maxLen] + '...')
            tItem.setToolTip(topic)
        else:
            tItem = QTableWidgetItem(topic)

        sItem = QTableWidgetItem(sender)

        for item in [dItem, tItem, sItem]:
            item.setBackground(QBrush(QColor('#2b5278')))

            if key is keyPsEncJson:
                item.setBackground(QBrush(QColor(Qt.darkGray)))

            if topic == TOPIC_PEERS:
                item.setBackground(QBrush(QColor(Qt.darkGreen)))
            elif topic == TOPIC_CHAT:
                item.setBackground(QBrush(QColor('#2b5278')))
            elif topic == TOPIC_LD_PRONTO:
                item.setBackground(QBrush(QColor(Qt.red)))

        viewButton = QToolButton(self)
        viewButton.setIcon(getIcon('search-engine.png'))
        viewButton.clicked.connect(functools.partial(
            self.viewJsonMessage, jsonMsg))

        for item in [dItem, tItem, sItem]:
            item.setFlags(
                Qt.ItemIsSelectable | Qt.ItemIsEnabled)

        curRow = self.tableWidget.rowCount()
        self.tableWidget.insertRow(curRow)
        self.tableWidget.setItem(curRow, 0, dItem)
        self.tableWidget.setItem(curRow, 1, tItem)
        self.tableWidget.setItem(curRow, 2, sItem)
        self.tableWidget.setCellWidget(curRow, 3, viewButton)

    def viewJsonMessage(self, msgJson):
        """
        :param message bytes: raw message data
        """

        dlg = QDialog()
        layout = QVBoxLayout()
        dlg.setLayout(layout)
        dlg.setMinimumSize(
            (2 * self.app.desktopGeometry.width()) / 3,
            (2 * self.app.desktopGeometry.height()) / 3,
        )

        msgView = QTextBrowser(dlg)
        msgView.setFontFamily('Montserrat')
        msgView.setFontWeight(QFont.DemiBold)
        msgView.setFontPointSize(12)
        layout.addWidget(msgView)
        msgView.insertPlainText(
            json.dumps(msgJson, indent=4))

        msgView.moveCursor(QTextCursor.Start)

        dlg.exec_()

    async def onClose(self):
        return True
