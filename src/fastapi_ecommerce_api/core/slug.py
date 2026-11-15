import re
from typing import Annotated, Self
import unicodedata

from pydantic import BaseModel, StringConstraints, model_validator

Slug = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)
]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


def slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")[:120].rstrip("-")


class NamedSluggedCreate(BaseModel):
    name: Name
    slug: Slug | None = None

    @model_validator(mode="after")
    def derive_slug(self) -> Self:
        if self.slug is None:
            self.slug = slugify(self.name)
            if not self.slug:
                raise ValueError("cannot derive a slug from the name, provide one")
        return self
