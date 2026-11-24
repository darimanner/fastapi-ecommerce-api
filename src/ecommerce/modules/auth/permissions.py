from collections.abc import Mapping
from enum import StrEnum

from ecommerce.modules.auth.models import Role


class Permission(StrEnum):
    BRANDS_WRITE = "brands:write"
    CATEGORIES_WRITE = "categories:write"
    PRODUCTS_WRITE = "products:write"


ROLE_PERMISSIONS: Mapping[Role, frozenset[Permission]] = {
    Role.CUSTOMER: frozenset(),
    Role.ADMIN: frozenset(Permission),
}
