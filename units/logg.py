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
    """Kapselt Einrichtung und Laufzeitänderung der Logging-Ausgabe."""

    LEVELS = {
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
    }

    @classmethod
    def normalize_level(cls, level):
        """Liefert einen unterstützten Levelnamen; unbekannte Werte werden INFO."""
        if isinstance(level, int):
            level = logging.getLevelName(level)
        if isinstance(level, str):
            level = level.upper()
        return level if level in cls.LEVELS else "INFO"

    @classmethod
    def set_level(cls, level):
        """Setzt Root-Logger und Handler auf denselben Level."""
        level_name = cls.normalize_level(level)
        log_level = cls.LEVELS[level_name]
        root = logging.getLogger()
        root.setLevel(log_level)
        for handler in root.handlers:
            handler.setLevel(log_level)
        return level_name

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
        LogManager.set_level(level)

