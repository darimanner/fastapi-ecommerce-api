from enum import StrEnum

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from ecommerce.core.db.mixins.timestamp import TimestampMixin
from ecommerce.core.db.mixins.uuid_pk import UUIDPrimaryKeyMixin
from ecommerce.core.db.model import Base


class Role(StrEnum):
    CUSTOMER = "customer"
    ADMIN = "admin"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Backs the schema-level lowercasing, so uniqueness is case-insensitive.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("role IN ('customer', 'admin')", name="role"),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(String(20), default=Role.CUSTOMER)
    is_active: Mapped[bool] = mapped_column(default=True)
