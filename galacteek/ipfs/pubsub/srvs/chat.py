import asyncio
import orjson

from galacteek import log
from galacteek import cached_property
from galacteek.config import cParentGet
from galacteek.config import merge as configMerge

from galacteek.ipfs.pubsub import TOPIC_CHAT

from galacteek.ipfs.pubsub.service import JSONPubsubService
from galacteek.ipfs.pubsub.service import RSAEncryptedJSONPubsubService
from galacteek.ipfs.pubsub.service import Curve25519JSONPubsubService

from galacteek.ipfs.pubsub.messages.chat import ChatRoomMessage
from galacteek.ipfs.pubsub.messages.chat import ChatStatusMessage
from galacteek.ipfs.pubsub.messages.chat import ChatChannelsListMessage
from galacteek.ipfs.pubsub.messages.chat import UserChannelsListMessage
from galacteek.ipfs.wrappers import ipfsOp

from galacteek.core.ps import keyChatChannels
from galacteek.core.ps import keyChatChanList
from galacteek.core.ps import keyChatChanUserList
from galacteek.core.ps import makeKeyPubChatTokens
from galacteek.core.ps import psSubscriber

from galacteek.core.chattokens import PubChatTokensManager
from galacteek.core.chattokens import verifyTokenPayload


class PSChatService(JSONPubsubService):
    def __init__(self, ipfsCtx, **kw):
        super(PSChatService, self).__init__(
            ipfsCtx, topic=TOPIC_CHAT,
            runPeriodic=True,
            **kw)
        self.pSubscriber = psSubscriber('ps-chat')
        self.pSubscriber.add_async_listener(
            keyChatChanList, self.onUserChannelList)

        self.chanUsers = {}
        self.tokManager = PubChatTokensManager()

        self.tokManager.sChanChanged.connectTo(self.onChanChanged)
        self.tokManager.sTokenStatus.connectTo(self.onTokenStatus)

    def config(self):
        base = super().config()
        return configMerge(base, cParentGet('services.chat'))

    @cached_property
    def cUserChannelsListMessage(self):
        return self.messageConfig('UserChannelsListMessage')

    async def start(self):
        await super().start()

        await self.tokManager.start()
        await self.scheduler.spawn(self.tokManager.cleanupTask())

    async def onChanChanged(self, pubchannel):
        await self.chatChanUserListPub(pubchannel)

    async def onTokenStatus(self, tokenCid, channel, status):
        key = makeKeyPubChatTokens(channel)
        await self.gHubPublish(
            key,
            (tokenCid, status)
        )

    async def peersByChannel(self, channel):
        async for token in self.tokManager.tokensByChannel(channel):
            yield token.peerId, token

    async def processJsonMessage(self, sender, msg, msgDbRecord=None):
        msgType = msg.get('msgtype', None)

        peerCtx = self.ipfsCtx.peers.getByPeerId(sender)
        if not peerCtx:
            self.debug('Message from unauthenticated peer: {}'.format(
                sender))
            return

        if msgType == ChatChannelsListMessage.TYPE:
            await self.handleChannelsListMessage(msg)

        elif msgType == UserChannelsListMessage.TYPE:
            await self.handleUserChannelsMessage(
                sender, peerCtx, msg, msgDbRecord)

    @ipfsOp
    async def onUserChannelList(self, ipfsop, key, msg):
        await self.send(msg)

    async def chatChanUserListPub(self, chan):
        pList = [p async for p in self.peersByChannel(chan)]

        await self.gHubPublish(
            keyChatChanUserList,
            (chan, pList)
        )

    @ipfsOp
    async def handleUserChannelsMessage(self, ipfsop, sender, piCtx, msg,
                                        dbRecord):
        msgConfig = self.cUserChannelsListMessage

        cMsg = UserChannelsListMessage(msg)
        if not cMsg.valid():
            return

        pubTokensList = cMsg.pubChannels if cMsg.pubChannels else []
        jwsCids = [c['sessionJwsCid'] for c in pubTokensList]

        for jwsCid in jwsCids:
            token = await self.tokManager.tokenGet(jwsCid)

            if token:
                await self.tokManager.tokenUpdate(token)
            else:
                # Fetch the JWS first
                jws = await ipfsop.getJson(
                    jwsCid, timeout=msgConfig.jwsFetchTimeout)

                if not jws:
                    log.debug(f'Could not fetch JWS with CID: {jwsCid}')
                    await ipfsop.sleep()
                    continue

                pubJwk = await piCtx.pubKeyJwk()
                if not pubJwk:
                    log.debug(f'Peer {sender}: waiting for JWK')
                    await ipfsop.sleep()
                    continue

                payload = await ipfsop.ctx.rsaExec.jwsVerify(
                    orjson.dumps(jws).decode(),
                    pubJwk
                )

                if not payload:
                    log.debug(f'Peer {sender}: invalid JWS payload')
                    await ipfsop.sleep()
                    continue

                jwsT = verifyTokenPayload(payload)

                if not jwsT:
                    log.debug(f'Peer {sender}: invalid JWS payload')
                    await ipfsop.sleep()
                    continue

                psTopic = jwsT.psTopic
                chan = jwsT.channel
                pubKeyCid = jwsT.pubKeyCid

                log.debug(f'Peer {sender}: valid JWS:'
                          f'sec topic: {psTopic}')

                if ipfsop.ourNode(sender):
                    await self.tokManager.reg(
                        jwsCid, chan, psTopic, sender,
                        pubKeyCid, encType=jwsT.encType,
                        did=jwsT.did)
                else:
                    if 0:
                        # Disabled for now cause listing peers
                        # on a topic is not always reliable ..

                        # Check who's subscribed to the topic
                        psPeers = await ipfsop.pubsubPeers(
                            topic=psTopic, timeout=5)

                        # There should only be one peer subscribed
                        if psPeers and len(psPeers) == 1:
                            await self.tokManager.reg(
                                jwsCid, chan, psTopic, sender,
                                pubKeyCid, encType=jwsT.encType,
                                did=jwsT.did)
                        else:
                            log.debug(f'Peer {sender}: valid JWS but '
                                      'no one listening on sectopic')

                    await self.tokManager.reg(
                        jwsCid, chan, psTopic, sender,
                        pubKeyCid, encType=jwsT.encType,
                        did=jwsT.did)

            await ipfsop.sleep()

        piCtx._processData['chatTokensLastRev'] = cMsg.rev

    @ipfsOp
    async def handleChannelsListMessage(self, ipfsop, msg):
        cMsg = ChatChannelsListMessage(msg)
        if not cMsg.valid():
            self.debug('Invalid channels message')
            return

        # Publish to the hub
        await self.gHubPublish(keyChatChannels, cMsg)

    @ipfsOp
    async def periodic(self, ipfsop):
        while True:
            msgConfig = self.messageConfig('ChatChannelsListMessage')

            await asyncio.sleep(msgConfig.sendInterval)

            if ipfsop.ctx.currentProfile:
                channelsDag = ipfsop.ctx.currentProfile.dagChatChannels

                await self.send(
                    ChatChannelsListMessage.make(channelsDag.channelsSorted)
                )

    async def shutdown(self):
        await super().shutdown()
        self.tokManager.active = False


class RSAPSEncryptedChatChannelService(RSAEncryptedJSONPubsubService):
    def __init__(self, ipfsCtx,
                 channel: str, topic: str,
                 jwsTokenCid, psKey, **kw):
        self.channel = channel
        self.psKey = psKey
        self.jwsTokenCid = jwsTokenCid
        self._chatPeers = []
        self.mChatService = ipfsCtx.pubsub.byTopic(TOPIC_CHAT)

        super(RSAPSEncryptedChatChannelService, self).__init__(
            ipfsCtx,
            topic,
            runPeriodic=True,
            peered=False,
            minMsgTsDiff=1,
            filterSelfMessages=False, **kw)

    async def processJsonMessage(self, sender, msg, msgDbRecord=None):
        msgType = msg.get('msgtype', None)

        peerCtx = self.ipfsCtx.peers.getByPeerId(sender)
        if not peerCtx:
            self.debug('Message from unauthenticated peer: {}'.format(
                sender))
            return

        if msgType == ChatRoomMessage.TYPE:
            await self.handleChatMessage(sender, peerCtx, msg)

    async def handleChatMessage(self, sender, peerCtx, msg):
        cMsg = ChatRoomMessage(msg)
        if not cMsg.valid():
            self.debug('Invalid chat message')
            return

        cMsg.peerCtx = peerCtx
        await self.gHubPublish(self.psKey, (sender, cMsg))

    async def peersToSend(self):
        async for peer, token in self.mChatService.peersByChannel(
                self.channel):
            piCtx = self.ipfsCtx.peers.getByPeerId(peer)
            if not piCtx:
                continue

            topic = token.secTopic
            yield (peer, piCtx, None, topic)

    async def processHeartbeat(self, sender, message):
        if sender not in self._chatPeers:
            self._chatPeers.append(sender)

    async def handleStatusMessage(self, sender, peerCtx, msg):
        sMsg = ChatStatusMessage(msg)
        if not sMsg.valid():
            self.debug('Invalid chat message')
            return

        sMsg.peerCtx = peerCtx
        await self.gHubPublish(self.psKey, sMsg)

    async def shutdown(self):
        await super().shutdown()
        await self.mChatService.tokManager.tokenDestroy(self.jwsTokenCid)


class PSEncryptedChatChannelService(Curve25519JSONPubsubService):
    def __init__(self, ipfsCtx,
                 channel: str, topic: str,
                 jwsTokenCid, privEccKey, psKey, **kw):
        super(PSEncryptedChatChannelService, self).__init__(
            ipfsCtx,
            topic,
            privEccKey,
            runPeriodic=True,
            peered=False,
            minMsgTsDiff=1,
            filterSelfMessages=False, **kw)

        self.channel = channel
        self.psKey = psKey
        self.privEccKey = privEccKey
        self.jwsTokenCid = jwsTokenCid

        self.mChatService = ipfsCtx.pubsub.byTopic(TOPIC_CHAT)

        self.pSubscriber = psSubscriber(topic)
        self.pSubscriber.add_sync_listener(
            keyChatChanUserList, self.onChatChanUserList)

    def onChatChanUserList(self, key, message):
        chan, chanList = message

        if chan != self.channel:
            return

        self._authorizedPeers = [peerId for peerId, token in chanList]

    async def processJsonMessage(self, sender, msg, msgDbRecord=None):
        msgType = msg.get('msgtype', None)

        peerCtx = self.ipfsCtx.peers.getByPeerId(sender)
        if not peerCtx:
            self.debug('Message from unauthenticated peer: {}'.format(
                sender))
            return

        if msgType == ChatRoomMessage.TYPE:
            await self.handleChatMessage(sender, peerCtx, msg)

    async def handleChatMessage(self, sender, peerCtx, msg):
        cMsg = ChatRoomMessage(msg)
        if not cMsg.valid():
            self.debug('Invalid chat message')
            return

        cMsg.peerCtx = peerCtx
        await self.gHubPublish(self.psKey, (sender, cMsg))

    async def peersToSend(self):
        async for peer, token in self.mChatService.peersByChannel(
                self.channel):
            piCtx = self.ipfsCtx.peers.getByPeerId(peer)
            if not piCtx:
                continue

            yield (piCtx, None, token.secTopic, token.pubKeyCid)

    async def handleStatusMessage(self, sender, peerCtx, msg):
        sMsg = ChatStatusMessage(msg)
        if not sMsg.valid():
            self.debug('Invalid chat message')
            return

        sMsg.peerCtx = peerCtx
        await self.gHubPublish(self.psKey, sMsg)

    async def shutdown(self):
        await super().shutdown()
        await self.mChatService.tokManager.tokenDestroy(self.jwsTokenCid)
