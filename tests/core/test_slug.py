from pydantic import ValidationError
import pytest

from fastapi_ecommerce_api.core.slug import NamedSluggedCreate, slugify


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Running Shoes & Socks!", "running-shoes-socks"),
        ("Café Noir", "cafe-noir"),
        ("  --Trail--  ", "trail"),
        ("Кофе", ""),
        ("Straße Łódź", "strasse-lodz"),
        ("Øresund Æble Œuvre", "oresund-aeble-oeuvre"),
    ],
)
def test_slugify(value: str, expected: str) -> None:
    assert slugify(value) == expected


def test_slug_is_derived_from_name() -> None:
    assert NamedSluggedCreate(name="Running Shoes").slug == "running-shoes"


def test_explicit_slug_is_kept() -> None:
    assert NamedSluggedCreate(name="Кофе", slug="coffee").slug == "coffee"


def test_malformed_explicit_slug_is_rejected() -> None:
    with pytest.raises(ValidationError, match="slug"):
        NamedSluggedCreate(name="Shoes", slug="Bad Slug")


def test_name_without_slug_material_asks_for_explicit_slug() -> None:
    with pytest.raises(ValidationError, match="provide one"):
        NamedSluggedCreate(name="!!!")
