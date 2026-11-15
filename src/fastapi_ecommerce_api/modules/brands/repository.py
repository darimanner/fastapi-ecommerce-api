from fastapi_ecommerce_api.infrastructure.repository import SQLAlchemyRepository
from fastapi_ecommerce_api.modules.brands.models import Brand


class BrandRepository(SQLAlchemyRepository[Brand]):
    model = Brand
