import logging
from logging.config import dictConfig

from .config import Settings


def configure_logging(settings: Settings) -> None:
    # Use DEBUG level when DEBUG=True, otherwise use configured LOG_LEVEL
    if settings.DEBUG and settings.LOG_LEVEL.upper() == "INFO":
        level = logging.DEBUG
    else:
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
                    "()": "vinc_api.common.middleware.RequestIDLogFilter",
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
            "loggers": {
                # Only show DEBUG logs for our debug middleware
                "vinc_api.debug": {
                    "level": logging.DEBUG,
                    "handlers": ["console"],
                    "propagate": False,
                },
                # Keep third-party libraries at INFO or WARNING
                "pymongo": {
                    "level": logging.WARNING,
                },
                "pymongo.topology": {
                    "level": logging.WARNING,
                },
                "pymongo.connection": {
                    "level": logging.WARNING,
                },
                "pymongo.serverSelection": {
                    "level": logging.WARNING,
                },
                "sqlalchemy": {
                    "level": logging.WARNING,
                },
                "sqlalchemy.engine": {
                    "level": logging.WARNING,
                },
                "httpx": {
                    "level": logging.WARNING,
                },
                "httpcore": {
                    "level": logging.WARNING,
                },
                "uvicorn": {
                    "level": logging.INFO,
                },
                "uvicorn.access": {
                    "level": logging.INFO,
                },
                "uvicorn.error": {
                    "level": logging.INFO,
                },
                "opentelemetry": {
                    "level": logging.WARNING,
                },
            },
        }
    )
