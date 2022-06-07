
from .objects import GObject
from .objects import pyqtSignal


from galacteek import AsyncSignal
from galacteek.ipfs.dag import EvolvingDAG


class DAGSignalsTower(GObject):
    dappDeployedAtCid = pyqtSignal(EvolvingDAG, str, str)


class URLSchemesTower(GObject):
    qMappingsChanged = AsyncSignal()


class DIDTower:
    didServiceOpenRequest = AsyncSignal(str, str, dict)
    didServiceObjectOpenRequest = AsyncSignal(
        str, str, str, _id='didObjectOpen')
