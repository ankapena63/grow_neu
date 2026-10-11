"""Verwaltet die zyklischen Abfragen der Energiegeräte."""


class GeraeteManager:
    """Führt Geräteabfragen in der festgelegten Reihenfolge aus."""

    def __init__(self, growatt, solax=None, hms=None, strom=None):
        # Übergangskompatibilität: ältere Aufrufer übergeben AppState.
        # Neue Aufrufer übergeben die Geräteobjekte direkt.
        if solax is None and hms is None and strom is None:
            app_state = growatt
            self.growatt = app_state.growatt
            self.solax = app_state.solax
            self.hms = app_state.hms
            self.strom = app_state.strom
        else:
            self.growatt = growatt
            self.solax = solax
            self.hms = hms
            self.strom = strom

    async def pruefe_geraete(self, zeit: float) -> None:
        # Reihenfolge beibehalten: Growatt, Solax, HMS, Strom.
        await self.growatt.pruefe(zeit)
        await self.solax.pruefe(zeit)
        await self.hms.pruefe(zeit)
        await self.strom.pruefe(zeit)
