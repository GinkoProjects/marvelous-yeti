import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

from my.commands import ProcessRunner
from my.plugins.common import (CommandGroup, Plugin, PluginLoader,
                               PluginRegistry)

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

TProcessRunner = TypeVar("TProcessRunner", bound="ProcessRunner")

logger = logging.getLogger(__name__)
plugin_loader = PluginLoader()


_loaded = []
for _plug_entrypoint in entry_points(group="my.plugins.command"):
    logger.info("loading command %s", _plug_entrypoint)
    plugin_loader.load_command(_plug_entrypoint)

for _plug_entrypoint in entry_points(group="my.plugins.process"):
    logger.info("loading process %s", _plug_entrypoint)
    plugin_loader.load_registry(_plug_entrypoint)


# Expose all plugins
for _plug_name, _plug in plugin_loader.plugins.items():
    globals()[_plug_name] = _plug
    _loaded.append(_plug_name)

globals()["plugins"] = plugin_loader
_loaded.append("plugins")

__all__ = _loaded

if __name__ == "__main__":
    from pprint import pprint

    pprint({pname: p.as_dict() for pname, p in plugin_loader.plugins.items()})
