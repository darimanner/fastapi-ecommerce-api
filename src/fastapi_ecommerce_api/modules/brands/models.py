from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_ecommerce_api.core.db.mixins.timestamp import TimestampMixin
from fastapi_ecommerce_api.core.db.mixins.uuid_pk import UUIDPrimaryKeyMixin
from fastapi_ecommerce_api.core.db.model import Base


class Brand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brands"

    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
