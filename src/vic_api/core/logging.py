import logging
from logging.config import dictConfig

from .config import Settings


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "logging.Formatter",
                    "format": "%(asctime)s %(levelname)s [%(name)s] [tenant=%(tenant_id)s trace=%(trace_id)s span=%(span_id)s req=%(request_id)s] %(message)s",
                }
            },
            "filters": {
                "request_id": {
                    "()": "vic_api.common.middleware.RequestIDLogFilter",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["request_id"],
                    "level": level,
                }
            },
            "root": {
                "handlers": ["console"],
                "level": level,
            },
        }
    )
