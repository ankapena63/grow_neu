"""Verwaltung der Sicherung der letzten 48 Stunden."""
import logging

from units.history import HistoryManager
from units.state import AppState

logger = logging.getLogger(__name__)


class BackupManager:
    """Speichert die aktuellen Energiedaten regelmäßig in aktuell.csv."""

    def __init__(self, app_state: AppState, history_manager: HistoryManager):
        self.app_state = app_state
        self.history_manager = history_manager

    async def pruefe_48st(self, zeit: float) -> None:
        """Leitet die Backup-Prüfung an den HistoryManager weiter."""
        await self.history_manager.pruefe_48st(zeit)
