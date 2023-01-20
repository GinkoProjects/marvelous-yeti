from typing import (Callable, Generator, Generic, List, Optional, Protocol,
                    TypeVar)

from fastapi import FastAPI

from ..bootstrap import bootstrap
from ..models import Event, Source

app = FastAPI()

uow = bootstrap()


@app.get("/")
def get_root():
    return {"Hello": "World"}


@app.get("/events/{event_id}")
def get_event(event_id: int):
    with uow:
        return uow.db.get_event(event_id)


@app.post("/events/")
def add_event(e: Event):
    with uow:
        uow.db.add_event(e)
        print("Contains event:", e in uow.session, uow.session)
        print("Contains source:", e.source in uow.session, uow.session)
        uow.commit()
