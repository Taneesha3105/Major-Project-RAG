import logging
import logging.config


def configure_logging(log_level: str = "INFO") -> None:
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            }
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
            }
        },
        "root": {
            "handlers": ["default"],
            "level": log_level.upper(),
        },
        "loggers": {
            "uvicorn": {
                "level": log_level.upper(),
            },
            "uvicorn.error": {
                "level": log_level.upper(),
            },
            "uvicorn.access": {
                "level": log_level.upper(),
            },
        },
    }

    logging.config.dictConfig(logging_config)
