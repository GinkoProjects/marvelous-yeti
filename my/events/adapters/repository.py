import abc
from typing import Set

from .. import models
from . import orm


class AbstractRepository(abc.ABC):
    def add_event(self, event: models.Event):
        self._add_event(event)

    def get_event(self, event_id: int) -> models.Event:
        return self._get_event(event_id)

    def add_source(self, source: models.Source):
        self._add_source(source)

    def get_source(self, source_name: str) -> models.Source:
        return self._get_source(source_name)

    @abc.abstractmethod
    def _add_event(self, event: models.Event):
        raise NotImplementedError

    @abc.abstractmethod
    def _get_event(self, event_id: int) -> models.Event:
        raise NotImplementedError

    @abc.abstractmethod
    def _add_source(self, source: models.Source):
        raise NotImplementedError

    @abc.abstractmethod
    def _get_source(self, source_name: str) -> models.Source:
        raise NotImplementedError


class SqlAlchemyRepository(AbstractRepository):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def _add_event(self, event):
        self.session.add(event)

    def _get_event(self, event_id):
        return self.session.query(models.Event).filter_by(id=event_id).first()

    def _add_source(self, source):
        self.session.add(source)

    def _get_source(self, source_name):
        return self.session.query(models.Source).filter_by(name=source_name).first()
