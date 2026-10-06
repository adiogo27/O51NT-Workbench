from __future__ import annotations

import json
import logging
import logging.config
from datetime import UTC, datetime
from pathlib import Path


class JsonlFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "dados", None)
        if extra:
            payload["dados"] = extra
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(logs_dir: Path) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "jsonl": {"()": JsonlFormatter},
                "console": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "console", "level": "INFO"},
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "jsonl",
                    "filename": str(logs_dir / "o51nt.jsonl"),
                    "maxBytes": 5_000_000,
                    "backupCount": 3,
                    "encoding": "utf-8",
                    "level": "INFO",
                },
            },
            "loggers": {
                "o51nt": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
            },
        }
    )
