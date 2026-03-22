from pydantic import BaseModel


class PaginationMeta(BaseModel):
    total_count: int
    offset: int
    limit: int | None
    returned_count: int
    has_more: bool
