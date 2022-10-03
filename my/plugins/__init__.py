import logging
import sys

from .common import *  # noqa
from .load import *  # noqa
from .load import PluginLoader

if sys.version_info < (3, 10):
    from importlib_metadata import EntryPoint, entry_points
else:
    from importlib.metadata import EntryPoint, entry_points

logger = logging.getLogger(__name__)


def load_plugins(loader):
    for _plug_entrypoint in entry_points(group="my.plugins.command"):
        logger.info("loading command %s", _plug_entrypoint)
        loader.load_command(_plug_entrypoint)

    for _plug_entrypoint in entry_points(group="my.plugins.process"):
        logger.info("loading process %s", _plug_entrypoint)
        loader.load_process(_plug_entrypoint)

    for _plug_entrypoint in entry_points(group="my.plugins.registry"):
        logger.info("loading registry %s", _plug_entrypoint)
        loader.load_registry(_plug_entrypoint)


def expose_plugins(loader):
    """Explose plugins the loader found"""
    loaded = []
    # Plugins are exposed by name
    for _plug_name, _plug in loader.plugins.items():
        globals()[_plug_name] = _plug
        loaded.append(_plug_name)

    # Expose loader
    globals()["loader"] = loader
    loaded.append("loader")

    return loaded


plugin_loader = PluginLoader()
load_plugins(plugin_loader)
__all__ = expose_plugins(plugin_loader)
