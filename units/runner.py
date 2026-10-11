"""Central scheduler for device polling and application control."""
from datetime import datetime
import logging
import time

from units.backup_manager import BackupManager
from units.calculations import TageswerteManager
from units.dazu import DazuManager
from units.kochen_manager import KochenManager
from units.geraete_manager import GeraeteManager
from units.zeit_manager import ZeitManager
from units.push import PushManager
from units.state import AppState

logger = logging.getLogger(__name__)


async def sende_dazu(app_state: AppState, wert):
    """Kompatibilität für bisherige Aufrufer."""
    manager = DazuManager(app_state)
    await manager.sende_dazu(wert)


async def rechne_dazu(app_state: AppState):
    """Kompatibilität für bisherige Aufrufer."""
    manager = DazuManager(app_state)
    await manager.rechne_dazu()


async def sende_ntfy(session, nachricht: str, prio: int) -> bool:
    """Kompatibilität für bisherige Aufrufer."""
    return await PushManager.sende_ntfy(session, nachricht, prio)


async def sende_push(
    app_state, nachricht, pause: int = 3600, prio: int = 3
):
    """Kompatibilität für bisherige Aufrufer."""
    manager = PushManager(app_state)
    await manager.sende_push(nachricht, pause, prio)


async def pruefe_kochen(app_state: AppState, zeit: float) -> None:
    """Kompatibilität für bisherige Aufrufer und Tests."""
    manager = KochenManager(app_state, rechne_dazu=rechne_dazu)
    await manager.pruefe_kochen(zeit)


async def pruefe_48st(app_state: AppState, zeit: float) -> None:
    """Kompatibilität für bisherige Aufrufer."""
    manager = BackupManager(app_state)
    await manager.pruefe_48st(zeit)


class AppRunner:
    def __init__(self, app_state: AppState):
        self.app_state = app_state

        self.tageswerte_manager = TageswerteManager(app_state)
        self.zeit_manager = ZeitManager(app_state)
        self.backup_manager = BackupManager(app_state)
        self.dazu_manager = DazuManager(app_state)
        self.kochen_manager = KochenManager(
            app_state, rechne_dazu=self._rechne_dazu
        )

        # Die vorhandenen Geräteobjekte werden direkt übergeben.
        self.geraete_manager = GeraeteManager(
            app_state.growatt,
            app_state.solax,
            app_state.hms,
            app_state.strom,
        )

    async def _rechne_dazu(self, app_state: AppState) -> None:
        await self.dazu_manager.rechne_dazu()

    async def wiederholte_takt(self):
        app_state = self.app_state

        await self.tageswerte_manager.reset_heute_werte()

        jetzt = datetime.now()
        zeit_jetzt = time.monotonic()

        self.zeit_manager.aktualisiere_zeitstatus(
            jetzt, zeit_jetzt
        )
        self.zeit_manager.pruefe_dazu_intervall(zeit_jetzt)

        await self.backup_manager.pruefe_48st(zeit_jetzt)

        if app_state._dose_manager is None:
            logger.warning("[Dose] Manager ist nicht initialisiert")
        else:
            await app_state._dose_manager.pruefe(zeit_jetzt)

        if app_state.kochen:
            await self.kochen_manager.pruefe_kochen(zeit_jetzt)

        await self.geraete_manager.pruefe_geraete(zeit_jetzt)

        app_state.erste_abfrage = False


async def wiederholte_takt(app_state: AppState):
    """Übergang für bestehende Aufrufer."""
    runner = AppRunner(app_state)
    await runner.wiederholte_takt()
