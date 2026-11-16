from ecommerce.config.settings import settings
from ecommerce.core.db.sessions import engine


def test_sql_parameters_stay_out_of_errors_unless_debug() -> None:
    # Error messages (and so logs) would otherwise carry submitted values.
    assert engine.sync_engine.hide_parameters is not settings.logger.debug
