from .adapters import orm
from .service import unit_of_work


def bootstrap(
    start_orm: bool = True, uow: unit_of_work.AbstractUnitOfWork = unit_of_work.SqlAlchemyUnitOfWork()
) -> unit_of_work.AbstractUnitOfWork:
    if start_orm:
        orm.start_mappers()

    return uow
