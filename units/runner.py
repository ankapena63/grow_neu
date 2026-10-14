"""Central scheduler for device polling and application control."""
from datetime import datetime
import logging
import time

from units.history import HistoryManager
from units.calculations import TageswerteManager
from units.dazu import DazuManager
from units.kochen_manager import KochenManager
from units.geraete_manager import GeraeteManager
from units.zeit_manager import ZeitManager
from units.state import AppState

class AppRunner:
    @classmethod
    def fuer(cls, app_state: AppState) -> "AppRunner":
        """Liefert den dauerhaft verwendeten Runner dieses AppState."""
        runner = app_state._app_runner
        if runner is None:
            runner = cls(app_state)
            app_state._app_runner = runner
        return runner

    def __init__(self, app_state: AppState):
        self.app_state = app_state

        self.tageswerte_manager = TageswerteManager.fuer(app_state)
        self.history_manager = HistoryManager.fuer(app_state)
        self.zeit_manager = ZeitManager(app_state)
        self.dazu_manager = DazuManager.fuer(app_state)
        self.kochen_manager = KochenManager(
            app_state, dazu_manager=self.dazu_manager
        )

        # Der Geräte-Manager steuert die Geräte desselben AppState.
        self.geraete_manager = GeraeteManager(app_state)

    async def wiederholte_takt(self):
        app_state = self.app_state

        await self.tageswerte_manager.reset_heute_werte()

        jetzt = datetime.now()
        zeit_jetzt = time.monotonic()

        self.zeit_manager.aktualisiere_zeitstatus(
            jetzt, zeit_jetzt
        )
        self.zeit_manager.pruefe_dazu_intervall(zeit_jetzt)

        await self.history_manager.pruefe_48st(zeit_jetzt)

        await self.geraete_manager.pruefe_dose(zeit_jetzt)

        if app_state.kochen:
            try:
                await self.kochen_manager.pruefe_kochen(zeit_jetzt)
            except Exception:
                # Ein Fehler in der Kochsteuerung darf die Geräteabfragen
                # dieses Takts nicht überspringen.
                logging.getLogger(__name__).exception(
                    "[Runner] Kochprüfung fehlgeschlagen."
                )

        await self.geraete_manager.pruefe_geraete(zeit_jetzt)

        app_state.erste_abfrage = False
