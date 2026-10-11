"""Verwaltung der Sicherung der letzten 48 Stunden."""
import logging

from units.history import speichere_aktuell_csv
from units.state import AppState

logger = logging.getLogger(__name__)


class BackupManager:
    """Speichert die aktuellen Energiedaten regelmäßig in aktuell.csv."""

    def __init__(self, app_state: AppState):
        self.app_state = app_state

    async def pruefe_48st(self, zeit: float) -> None:
        app_state = self.app_state
        if not app_state.einstellungen.get("aktuell_aktiv", True):
            return

        takt = app_state.takt_48_datei
        if zeit == 0 or zeit - app_state.aktuell_letztes_speichern >= takt:
            try:
                logger.info(
                    "💾 [Backup] Speichere 2 stündliches Aktuell-Daten-Backup..."
                )
                await speichere_aktuell_csv(app_state)
            except Exception:
                logger.error("❌ Fehler beim Backup-CSV-Speichern")
            finally:
                if zeit != 0:
                    app_state.aktuell_letztes_speichern = zeit
