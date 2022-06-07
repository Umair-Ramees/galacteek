from multiaddr import Multiaddr

from galacteek import log


def multiAddrTcp4(maddr):
    ipaddr, port = None, 0

    try:
        multi = Multiaddr(maddr)
    except BaseException as err:
        log.debug(f'Invalid multiaddr {maddr}, error: {err}')
        return ipaddr, port

    for proto in multi.protocols():
        if proto.name == 'ip4':
            ipaddr = multi.value_for_protocol(proto.code)
        if proto.name == 'tcp':
            port = int(multi.value_for_protocol(proto.code))

    return ipaddr, port
