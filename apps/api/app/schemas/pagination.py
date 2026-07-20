from pydantic import BaseModel


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int


def paginate_params(page: int = 1, page_size: int = 20) -> tuple[int, int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    return page, page_size
