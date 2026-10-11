"""Verwaltet die zyklischen Abfragen der Energiegeräte."""
from units.state import AppState


class GeraeteManager:
    """Führt Geräteabfragen in der festgelegten Reihenfolge aus."""

    def __init__(self, app_state: AppState):
        self.app_state = app_state

    async def pruefe_geraete(self, zeit: float) -> None:
        app_state = self.app_state

        # Reihenfolge beibehalten: Growatt, Solax, HMS, Strom.
        await app_state.growatt.pruefe(zeit)
        await app_state.solax.pruefe(zeit)
        await app_state.hms.pruefe(zeit)
        await app_state.strom.pruefe(zeit)
