from fastapi import Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class PageParams:
    def __init__(
        self,
        page: int = Query(1, ge=1),
        size: int = Query(20, ge=1, le=100),
    ):
        self.page = page
        self.size = size


def paginate(db: Session, query, params: PageParams) -> tuple[list, int]:
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.limit(params.size).offset((params.page - 1) * params.size)).all()
    return items, total
