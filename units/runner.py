"""Central scheduler for device polling and application control."""
from datetime import datetime
import logging
import time
from units.backup_manager import BackupManager
from units.calculations import reset_heute_werte
from units.dazu import DazuManager
from units.kochen_manager import KochenManager
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
    app_state,
    nachricht,
    pause: int = 3600,
    prio: int = 3,
):
    """Kompatibilität für bisherige Aufrufer."""
    manager = PushManager(app_state)
    await manager.sende_push(nachricht, pause, prio)


def stunden_bis_nacht_get(app_state: AppState) -> float:
    """Kompatibilität für bisherige Aufrufer."""
    manager = ZeitManager(app_state)
    return manager.stunden_bis_nacht_get()


async def pruefe_kochen(app_state: AppState, zeit: float) -> None:
    """Kompatibilität für bisherige Aufrufer."""
    manager = KochenManager(app_state)
    await manager.pruefe_kochen(zeit)

def pruefe_dazu_intervall(app_state: AppState, zeit: float) -> None:
    """Kompatibilität für bisherige Aufrufer."""
    manager = ZeitManager(app_state)
    manager.pruefe_dazu_intervall(zeit)


async def pruefe_48st(app_state: AppState, zeit: float) -> None:
    """Kompatibilität für bisherige Aufrufer."""
    manager = BackupManager(app_state)
    await manager.pruefe_48st(zeit)


class AppRunner:
    """Steuert den regelmäßigen Ablauf der Geräteabfragen."""

    def __init__(self, app_state: AppState):
        self.app_state = app_state

    async def wiederholte_takt(self) -> None:
        app_state = self.app_state

        await reset_heute_werte(app_state)

        jetzt = datetime.now()
        now = jetzt.strftime("%H:%M")
        zeit_jetzt = time.monotonic()

        app_state.nachtzeit = (
            app_state.startnacht <= now
            or now <= app_state.endnacht
        )

        app_state.stunden_bis_nacht = (
            stunden_bis_nacht_get(app_state)
        )

        app_state.benutzer_activ = (
            zeit_jetzt - app_state.last_activity
            < app_state.einstellungen.get(
                "takt_benutzrer_activ", 10
            )
        )

        pruefe_dazu_intervall(app_state, zeit_jetzt)
        await pruefe_48st(app_state, zeit_jetzt)

        # Dose bleibt unverändert.
        if app_state._dose_manager is None:
            logger.warning(
                "[Dose] Manager ist nicht initialisiert"
            )
        else:
            await app_state._dose_manager.pruefe(zeit_jetzt)

        # Kochen bleibt unverändert.
        if app_state.kochen:
            await pruefe_kochen(app_state, zeit_jetzt)

        # Geräteabfragen in der bisherigen Reihenfolge.
        await app_state.growatt.pruefe(zeit_jetzt)
        await app_state.solax.pruefe(zeit_jetzt)
        await app_state.hms.pruefe(zeit_jetzt)
        await app_state.strom.pruefe(zeit_jetzt)

        app_state.erste_abfrage = False


async def wiederholte_takt(app_state: AppState) -> None:
    """Übergang für bestehende Aufrufer."""
    runner = AppRunner(app_state)
    await runner.wiederholte_takt()
