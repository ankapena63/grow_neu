"""Central scheduler for device polling and application control."""
from datetime import datetime
import logging
import time

from units.backup_manager import BackupManager
from units.history import get_history_manager
from units.calculations import get_tageswerte_manager
from units.dazu import get_dazu_manager
from units.kochen_manager import KochenManager
from units.geraete_manager import GeraeteManager
from units.zeit_manager import ZeitManager
from units.state import AppState

logger = logging.getLogger(__name__)


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
        self.history_manager = get_history_manager(app_state)
        self.zeit_manager = ZeitManager(app_state)
        self.backup_manager = BackupManager(app_state, self.history_manager)
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
