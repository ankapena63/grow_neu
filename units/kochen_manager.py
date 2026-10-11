"""Verwaltung der Kochen-Funktion."""
import logging

from units.dazu import DazuManager
from units.state import AppState

logger = logging.getLogger(__name__)


class KochenManager:
    """Prüft Laufzeit, Mindest-SOC und Nachtabschaltung beim Kochen."""

    def __init__(self, app_state: AppState, rechne_dazu=None):
        self.app_state = app_state
        self._rechne_dazu_callback = rechne_dazu

    async def _rechne_dazu(self) -> None:
        if self._rechne_dazu_callback is not None:
            await self._rechne_dazu_callback(self.app_state)
        else:
            await DazuManager(self.app_state).rechne_dazu()

    async def pruefe_kochen(self, zeit: float) -> None:
        app_state = self.app_state
        soc = app_state.soc
        verbleibend = app_state.kochen_end - zeit

        if (
            soc < app_state.einstellungen.get("kochen_soc_min", 30)
            or verbleibend <= 0
        ):
            app_state.kochen = False
            app_state.kochen_zeit = 0.0
            await self._rechne_dazu()
            logger.info("KOCHEN AUS: SOC zu niedrig oder _Zeit abgelaufen")
            return

        if (
            app_state.nachtzeit
            and app_state.einstellungen.get("nacht_nur_0_schalter", False)
        ):
            logger.info("KOCHEN AUS:Nachts nur 0 Einp.")
            app_state.kochen = False
            app_state.kochen_zeit = 0.0
            await DazuManager(app_state).rechne_dazu()
            return

        app_state.kochen_zeit = round(verbleibend / 60, 2)
