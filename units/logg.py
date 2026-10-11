"""Zentrale Einrichtung der Konsolen- und HTML-Logs."""
import logging
from collections import deque

log_buffer = deque(maxlen=500)


class HtmlLogHandler(logging.Handler):
    def emit(self, record):
        try:
            nachricht = self.format(record)
            log_buffer.append(nachricht)
        except Exception:
            pass


class LogManager:
    """Kapselt die Einrichtung der Logging-Ausgabe."""

    @staticmethod
    def setup(level=logging.INFO):
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S",
        )

        html_handler = HtmlLogHandler()
        html_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(html_handler)
        root.addHandler(console_handler)
        root.setLevel(level)


def setup_logging(level=logging.INFO):
    """Kompatibilität für bestehende Aufrufer."""
    LogManager.setup(level)
