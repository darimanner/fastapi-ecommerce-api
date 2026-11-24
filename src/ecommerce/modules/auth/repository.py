from sqlalchemy import select

from ecommerce.infrastructure.repository import SQLAlchemyRepository
from ecommerce.modules.auth.models import User


class UserRepository(SQLAlchemyRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))
