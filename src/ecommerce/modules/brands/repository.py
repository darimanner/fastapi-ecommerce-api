from ecommerce.infrastructure.repository import SQLAlchemyRepository
from ecommerce.modules.brands.models import Brand


class BrandRepository(SQLAlchemyRepository[Brand]):
    model = Brand
