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
            app_state.growatt,
            app_state.solax,
            app_state.hms,
            app_state.strom,
        )
        for geraet in geraete:
            await geraet.pruefe(zeit)
