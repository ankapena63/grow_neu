"""Central scheduler for device polling and application control."""
from datetime import datetime
import logging
import time

from units.backup_manager import BackupManager
from units.calculations import get_tageswerte_manager
from units.dazu import DazuManager
from units.kochen_manager import KochenManager
from units.geraete_manager import GeraeteManager
from units.zeit_manager import ZeitManager
from units.push import PushManager
from units.state import AppState

logger = logging.getLogger(__name__)


def get_dazu_manager(app_state: AppState) -> DazuManager:
    """Liefert den dauerhaft verwendeten DazuManager dieses AppState."""
    manager = getattr(app_state, "_dazu_manager", None)
    if manager is None:
        manager = DazuManager(app_state)
        app_state._dazu_manager = manager
    return manager


async def sende_dazu(app_state: AppState, wert):
    """Kompatibilität für bisherige Aufrufer."""
    manager = get_dazu_manager(app_state)
    await manager.sende_dazu(wert)


async def rechne_dazu(app_state: AppState):
    """Kompatibilität für bisherige Aufrufer."""
    manager = get_dazu_manager(app_state)
    await manager.rechne_dazu()


async def sende_ntfy(session, nachricht: str, prio: int) -> bool:
    """Kompatibilität für bisherige Aufrufer."""
    return await PushManager.sende_ntfy(session, nachricht, prio)


async def sende_push(
    app_state, nachricht, pause: int = 3600, prio: int = 3
):
    """Kompatibilität für bisherige Aufrufer mit dauerhaftem PushManager."""
    manager = getattr(app_state, "_push_manager", None)
    if manager is None:
        manager = PushManager(app_state)
        app_state._push_manager = manager

    await manager.sende_push(nachricht, pause, prio)


async def pruefe_kochen(app_state: AppState, zeit: float) -> None:
    """Kompatibilität für bisherige Aufrufer und Tests."""
    runner = getattr(app_state, "_app_runner", None)
    if runner is not None:
        manager = runner.kochen_manager
    else:
        manager = getattr(app_state, "_kochen_manager", None)
        if manager is None:
            manager = KochenManager(
                app_state,
                rechne_dazu=lambda state: rechne_dazu(state),
            )
            app_state._kochen_manager = manager

    await manager.pruefe_kochen(zeit)


def get_backup_manager(app_state: AppState) -> BackupManager:
    """Liefert den dauerhaft verwendeten BackupManager dieses AppState."""
    manager = getattr(app_state, "_backup_manager", None)
    if manager is None:
        manager = BackupManager(app_state)
        app_state._backup_manager = manager
    return manager


async def pruefe_48st(app_state: AppState, zeit: float) -> None:
    """Kompatibilität für bisherige Aufrufer."""
    manager = get_backup_manager(app_state)
    await manager.pruefe_48st(zeit)


def get_app_runner(app_state: AppState) -> "AppRunner":
    """Liefert den dauerhaft verwendeten Runner für diesen AppState."""
    runner = getattr(app_state, "_app_runner", None)
    if runner is None:
        runner = AppRunner(app_state)
        app_state._app_runner = runner
    return runner


class AppRunner:
    def __init__(self, app_state: AppState):
        self.app_state = app_state

        self.tageswerte_manager = get_tageswerte_manager(app_state)
        self.zeit_manager = ZeitManager(app_state)
        self.backup_manager = get_backup_manager(app_state)
        self.dazu_manager = get_dazu_manager(app_state)
        self.kochen_manager = KochenManager(
            app_state, dazu_manager=self.dazu_manager
        )

        # Die vorhandenen Geräteobjekte werden direkt übergeben.
        self.geraete_manager = GeraeteManager(
            app_state.growatt,
            app_state.solax,
            app_state.hms,
            app_state.strom,
        )

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
    runner = get_app_runner(app_state)
    await runner.wiederholte_takt()
