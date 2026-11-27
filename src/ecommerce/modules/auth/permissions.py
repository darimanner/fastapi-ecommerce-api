from collections.abc import Mapping
from enum import StrEnum

from ecommerce.modules.auth.models import Role


class Permission(StrEnum):
    BRANDS_WRITE = "brands:write"
    CART_MANAGE = "cart:manage"
    CATEGORIES_WRITE = "categories:write"
    PRODUCTS_WRITE = "products:write"


ROLE_PERMISSIONS: Mapping[Role, frozenset[Permission]] = {
    Role.CUSTOMER: frozenset({Permission.CART_MANAGE}),
    Role.ADMIN: frozenset(Permission),
}
