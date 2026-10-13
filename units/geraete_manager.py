"""Verwaltet die zyklischen Abfragen der Energiegeräte."""


class GeraeteManager:
    """Führt Geräteabfragen in der festgelegten Reihenfolge aus."""

    def __init__(self, growatt, solax, hms, strom):
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
