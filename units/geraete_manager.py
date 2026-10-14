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
        try:
            await manager.pruefe(zeit)
        except Exception:
            logger.exception(
                "[Dose] Prüfung fehlgeschlagen; "
                "die übrigen Abläufe werden fortgesetzt."
            )

    async def pruefe_geraete(self, zeit: float) -> None:
        """Prüft die übrigen Energiegeräte nacheinander."""
        app_state = self.app_state
        geraete = (
            ("Growatt", getattr(app_state, "growatt", None)),
            ("Solax", getattr(app_state, "solax", None)),
            ("HMS", getattr(app_state, "hms", None)),
            ("Strom", getattr(app_state, "strom", None)),
        )
        # Ein noch nicht initialisiertes oder ausgefallenes Gerät darf
        # die Abfragen der anderen Geräte nicht verhindern.
        for name, geraet in geraete:
            if geraet is None:
                logger.warning(
                    "[Geräte] %s ist noch nicht initialisiert; "
                    "Abfrage wird übersprungen.",
                    name,
                )
                continue
            try:
                await geraet.pruefe(zeit)
            except Exception:
                logger.exception(
                    "[Geräte] Prüfung von %s fehlgeschlagen; "
                    "die übrigen Geräte werden weiter geprüft.",
                    name,
                )
