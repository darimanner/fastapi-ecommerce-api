import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ecommerce.core.db.mixins.timestamp import TimestampMixin
from ecommerce.core.db.mixins.uuid_pk import UUIDPrimaryKeyMixin
from ecommerce.core.db.model import Base


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    # No ON DELETE action: deleting a node that still has children is a 409.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id"), index=True
    )
