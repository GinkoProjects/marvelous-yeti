import argparse
from dataclasses import dataclass
from typing import Any, Dict, List, Set
from dynaconf.utils import DynaconfDict
from dynaconf import Dynaconf
from dynaconf.loaders import toml_loader
from pathlib import Path

import pytest


@pytest.fixture
def sample_config() -> Dynaconf:
    conf = DynaconfDict({}, env='development')
    config_file = Path(__file__).parent / "sample_config.toml"
    assert config_file.exists()
    toml_loader.load(conf, filename=config_file.absolute().as_posix(), env='development')
    return conf

def test_sample_config(sample_config):
    assert sample_config.my.debug == False
    assert sample_config.loaded_by_loaders["toml"]["MY"] != {}
