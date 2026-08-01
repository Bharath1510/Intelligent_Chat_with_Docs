import logging
import json
import contextvars
import sys
from datetime import datetime, timezone

correlation_id_ctx = contextvars.ContextVar("correlation_id", default="N/A")

# uvicorn installs its own handlers; without this its lines bypass the JSON format.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_object = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_ctx.get(),
        }
        if record.exc_info:
            log_object["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_object)


def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # clear() not a removeHandler loop — mutating the list while iterating it
    # skips every second handler and log lines end up duplicated.
    for handler in list(root.handlers):
        handler.close()
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)

    for name in _UVICORN_LOGGERS:
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True


logger = logging.getLogger("app")
