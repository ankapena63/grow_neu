"""Web routes grouped by feature while sharing the original blueprint."""

import logging
from quart import Blueprint, current_app
from ..config import DATA_DIR
from ..state import AppState

__all__ = ["routes", "_app_state", "explorer", "settings", "dashboard", "api"]

routes = Blueprint("routes", __name__)
logger = logging.getLogger(__name__)
BASE_DIR = DATA_DIR.parent
HOME_DIR = BASE_DIR

def _app_state() -> AppState:
    return current_app.extensions["app_state"]

from . import explorer
from . import settings
from . import dashboard
from . import api
