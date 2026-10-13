"""Verwaltung der Push-Benachrichtigungen."""
import logging
import time

from units.configuration import mache_session

logger = logging.getLogger(__name__)


class PushManager:
    """Versendet Push-Nachrichten und verwaltet die Pausen."""

    def __init__(self, app_state):
        self.app_state = app_state

    @staticmethod
    async def sende_ntfy(session, nachricht: str, prio: int) -> bool:
        headers = {
            "Priority": str(prio),
            "Title": "Solar-Monitor",
            "Tags": "warning" if prio >= 4 else "info",
        }
        url = "https://ntfy.sh/SolaxHmsGrowattvvv"

        async with session.post(
            url,
            data=nachricht.encode("utf-8"),
            headers=headers,
        ) as response:
            if response.status == 200:
                logger.info("✅ Push Prio: %s gesendet", prio)
                return True

            error_text = await response.text()
            logger.error(
                "❌ ntfy Fehler %s : %s",
                response.status,
                error_text,
            )
            return False

    async def sende_push(
        self,
        nachricht,
        pause: int = 3600,
        prio: int = 3,
    ):
        app_state = self.app_state

        if not app_state.einstellungen.get("nachricht_app", False):
            return

        jetzt = time.time()
        if not hasattr(app_state, "letzte_push_zeiten"):
            app_state.letzte_push_zeiten = {}

        letzte_zeit = app_state.letzte_push_zeiten.get(prio, 0)
        if jetzt - letzte_zeit < pause:
            return

        session = await mache_session(app_state, "session_push")
        try:
            if await self.sende_ntfy(session, nachricht, prio):
                app_state.letzte_push_zeiten[prio] = jetzt
        except Exception:
            logger.exception("❌ Push-Verbindung fehlgeschlagen")



def get_push_manager(app_state) -> PushManager:
    """Liefert den dauerhaft verwendeten PushManager dieses AppState."""
    manager = getattr(app_state, "_push_manager", None)
    if manager is None:
        manager = PushManager(app_state)
        app_state._push_manager = manager
    return manager
