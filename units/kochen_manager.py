"""Verwaltung der Kochen-Funktion."""
import logging

from units.dazu import DazuManager
from units.state import AppState

logger = logging.getLogger(__name__)


class KochenManager:
    """Prüft Laufzeit, Mindest-SOC und Nachtabschaltung beim Kochen."""

    def __init__(
        self,
        app_state: AppState,
        dazu_manager: DazuManager,
    ):
        self.app_state = app_state
        self.dazu_manager = dazu_manager

    async def _beende_kochen(self, meldung: str) -> None:
        """Beendet Kochen und berechnet die erforderliche Leistung neu."""
        self.app_state.kochen = False
        self.app_state.kochen_zeit = 0.0
        await self.dazu_manager.rechne_dazu()
        logger.info(meldung)

    async def pruefe_kochen(self, zeit: float) -> None:
        """Prüft die Kochdauer, den Mindest-SOC und die Nachtregel."""
        app_state = self.app_state
        verbleibend = app_state.kochen_end - zeit

        if (
            app_state.soc < app_state.einstellungen.get("kochen_soc_min", 30)
            or verbleibend <= 0
        ):
            await self._beende_kochen(
                "KOCHEN AUS: SOC zu niedrig oder Zeit abgelaufen"
            )
            return

        if (
            app_state.nachtzeit
            and app_state.einstellungen.get("nacht_nur_0_schalter", False)
        ):
            await self._beende_kochen("KOCHEN AUS: Nachts nur 0 Einspeisung")
            return

        app_state.kochen_zeit = round(verbleibend / 60, 2)
