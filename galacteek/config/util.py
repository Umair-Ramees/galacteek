import os
import sys
import traceback

from omegaconf import OmegaConf
from omegaconf import dictconfig

from pathlib import Path


class ConfigError(Exception):
    pass


def merge(*cfgs):
    try:
        return OmegaConf.merge(*cfgs)
    except Exception:
        traceback.print_exc()
        return None


def ocToContainer(cfg, resolve=True):
    return OmegaConf.to_container(cfg, resolve=resolve)


def environment():
    return {
        'env': os.environ.get(
            'GALACTEEK_ENV', 'mainnet'),
        'rdfgraphenv': os.environ.get(
            'GALACTEEK_PRONTO_CHAINENV', 'beta'),
        'ethenv': os.environ.get(
            'GALACTEEK_ETHNETWORK_ENV', 'rinkeby'),
    }


def empty():
    return OmegaConf.create({})


def load(configPath: Path, envConf: dict = None) -> dictconfig.DictConfig:
    # global genvs, ethEnvs
    genvs = 'envs'
    ethEnvsKey = 'ethEnvs'
    graphEnvsKey = 'graphEnvs'

    envConf = envConf if envConf else environment()
    env = envConf['env']
    ethEnv = envConf['ethenv']
    graphEnv = envConf['rdfgraphenv']

    try:
        base = empty()
        config = OmegaConf.load(str(configPath))

        envs = config.get(genvs, None)
        if envs:
            default = envs.get('default', None)
            if default:
                base = merge(base, default)

            if env not in envs:
                envs[env] = default
                base = envs[env]
            else:
                base = merge(base, envs.get(env))

        # Eth
        genvs = config.get(ethEnvsKey, None)
        if genvs:
            default = genvs.get('default', None)
            if default:
                base = merge(base, default)

            if ethEnv in genvs:
                base = merge(base, genvs.get(ethEnv))

        # RDF graphs
        graphenvs = config.get(graphEnvsKey, None)
        if graphenvs:
            default = graphenvs.get('default', None)
            if default:
                base = merge(base, default)

            if graphEnv in graphenvs:
                base = merge(base, graphenvs.get(graphEnv))
    except Exception as err:
        print(f'Error parsing config file {configPath}: {err}',
              file=sys.stderr)
        return None, None
    else:
        return config, base


def configFromFile(fpath: Path,
                   env_name: str = None) -> dictconfig.DictConfig:
    envConf = environment()
    top = empty()

    configAll, config = load(str(fpath), envConf)

    if config:
        top = merge(config, top)

    if not top:
        return None, None

    return configAll, top


def dictDotLeaves(dic: dict, parent=None, leaves=None):
    """
    For a dictionary, return the list of leaf nodes,
    using a dot-style notation

    :rtype: list

    """
    leaves = leaves if isinstance(leaves, list) else []

    for node, subnode in dic.items():
        if isinstance(subnode, dict):
            dictDotLeaves(
                subnode,
                parent=f'{parent}.{node}' if parent else node,
                leaves=leaves
            )
        else:
            leaves.append(f'{parent}.{node}' if parent else node)

    return leaves
