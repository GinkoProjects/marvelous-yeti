from dataclasses import field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import (Callable, Generator, Generic, List, Optional, Protocol,
                    TypeVar)

from fastapi import FastAPI
from pydantic.dataclasses import dataclass


@dataclass
class Source:
    name: str


@dataclass
class Event:
    name: str
    source: Source
    created: datetime = field(default_factory=datetime.now)
