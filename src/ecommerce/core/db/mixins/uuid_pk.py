import uuid

from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    # UUIDv7 is time-ordered: not enumerable in URLs, yet keeps index inserts local.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
