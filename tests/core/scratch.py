import uuid

from sqlalchemy import CheckConstraint, ForeignKey, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from fastapi_ecommerce_api.core.db.mixins.uuid_pk import UUIDPrimaryKeyMixin
from fastapi_ecommerce_api.core.db.model import Base
from fastapi_ecommerce_api.infrastructure.repository import SQLAlchemyRepository


class ScratchBase(DeclarativeBase):
    # Own metadata: the Alembic check in tests/conftest.py must not see these tables.
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)


class Widget(UUIDPrimaryKeyMixin, ScratchBase):
    __tablename__ = "widgets"
    __table_args__ = (CheckConstraint("qty >= 0", name="qty_non_negative"),)

    name: Mapped[str] = mapped_column(unique=True)
    qty: Mapped[int] = mapped_column(default=0)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("widgets.id"))


class WidgetRepository(SQLAlchemyRepository[Widget]):
    model = Widget
