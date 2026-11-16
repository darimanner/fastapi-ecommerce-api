import importlib
import importlib.util
import pkgutil


def import_all_models() -> None:
    """Import every `modules/<name>/models.py` so `Base.metadata` holds all tables."""
    for module in pkgutil.iter_modules(__path__):
        name = f"{__name__}.{module.name}.models"
        if module.ispkg and importlib.util.find_spec(name):
            importlib.import_module(name)
