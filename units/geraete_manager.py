"""Verwaltet die zyklischen Abfragen der Energiegeräte."""

from units.state import AppState


class GeraeteManager:
    """Steuert die vorhandenen Geräteobjekte eines AppState."""

    def __init__(self, app_state: AppState):
        self.app_state = app_state

    async def pruefe_geraete(self, zeit: float) -> None:
        # Ein gemeinsamer Ablauf hält Reihenfolge und Fehlerverhalten stabil.
        # Die Geräte werden nacheinander geprüft, nicht parallel.
        app_state = self.app_state
        geraete = (
            app_state.growatt,
            app_state.solax,
            app_state.hms,
            app_state.strom,
        )
        for geraet in geraete:
            await geraet.pruefe(zeit)
