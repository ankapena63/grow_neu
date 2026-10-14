"""Verwaltet die zyklischen Abfragen der Energiegeräte."""

import logging

from units.state import AppState

logger = logging.getLogger(__name__)


class GeraeteManager:
    """Steuert die vorhandenen Geräteobjekte eines AppState."""

    def __init__(self, app_state: AppState):
        self.app_state = app_state

    async def pruefe_dose(self, zeit: float) -> None:
        """Prüft die vorhandene Dose, sofern sie initialisiert ist."""
        manager = self.app_state._dose_manager
        if manager is None:
            logger.warning("[Dose] Manager ist nicht initialisiert")
            return
        await manager.pruefe(zeit)

    async def pruefe_geraete(self, zeit: float) -> None:
        """Prüft die übrigen Energiegeräte nacheinander."""
        app_state = self.app_state
        geraete = (
            ("Growatt", app_state.growatt),
            ("Solax", app_state.solax),
            ("HMS", app_state.hms),
            ("Strom", app_state.strom),
        )
        # Ein ausgefallenes Gerät darf die Abfragen der anderen Geräte
        # in diesem Takt nicht verhindern.
        for name, geraet in geraete:
            try:
                await geraet.pruefe(zeit)
            except Exception:
                logger.exception(
                    "[Geräte] Prüfung von %s fehlgeschlagen; "
                    "die übrigen Geräte werden weiter geprüft.",
                    name,
                )
