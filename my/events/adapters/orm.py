import logging

from sqlalchemy import (Column, Date, DateTime, ForeignKey, Integer, MetaData,
                        String, Table, event)
from sqlalchemy.orm import registry, relationship

from .. import models

# Adapted from https://github.com/cosmicpython/code/blob/69a88f8e05d549cc4cf01a91cd33b0fc4d87014d/src/allocation/adapters/orm.py

logger = logging.getLogger(__name__)

mapper_registry = registry()
metadata = mapper_registry.metadata

sources = Table("sources", metadata, Column("name", String(255), primary_key=True))

events = Table(
    "events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255)),
    Column("source", ForeignKey("sources.name")),
    Column("created", DateTime, nullable=False),
)


def start_mappers():
    logger.info("Starting mappers")
    source_mapper = mapper_registry.map_imperatively(models.Source, sources)
    event_mapper = mapper_registry.map_imperatively(
        models.Event, events
    )  # , properties={"source": relationship(source_mapper)})
