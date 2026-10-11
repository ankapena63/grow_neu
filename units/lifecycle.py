import asyncio
import logging
import os
import time

from quart import Quart

from units.config import STANDARD_EINSTELLUNGEN, STANDARD_ZUGANG
from units.calculations import astro_werte, get_nachtzeten
from units.configuration import lade_einstellungen, lade_zugang, mache_session
from units.history import lade_aktuell_csv
from units.runner import get_app_runner, pruefe_48st
from units.unit_battery import GrowattSessionManager
from units.logg import setup_logging
from units.state import AppState

logger = logging.getLogger(__name__)


class LifecycleManager:
    """Kapselt Konfiguration, Start und geordnetes Beenden."""

    def configure_logging(self, app_state: AppState) -> None:
        """Richtet das Logging anhand der Einstellungen ein."""
        levels = {
            "ERROR": logging.ERROR,
            "WARNING": logging.WARNING,
            "INFO": logging.INFO,
            "DEBUG": logging.DEBUG,
        }

        app_state.log_level = app_state.einstellungen.get(
            "log_level", "INFO"
        ).upper()
        log_level = levels.get(app_state.log_level, logging.INFO)

        setup_logging(log_level)

        root = logging.getLogger()
        root.setLevel(log_level)

        for handler in root.handlers:
            handler.setLevel(log_level)

        logging.getLogger("tinytuya").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.ERROR)
        logging.getLogger("hypercorn").setLevel(logging.WARNING)
        logging.getLogger("quart").setLevel(logging.WARNING)

    def load_configuration(self, app_state: AppState) -> None:
        """Lädt Einstellungen, Zugangsdaten und Growatt-Zugang."""
        try:
            app_state.einstellungen = lade_einstellungen(
                STANDARD_EINSTELLUNGEN
            )
        except Exception:
            logger.exception(
                "[Fehler beim Laden der Einstellungen] "
                "Standardwerte werden verwendet."
            )
            app_state.einstellungen = STANDARD_EINSTELLUNGEN.copy()

        for key, default in STANDARD_EINSTELLUNGEN.items():
            app_state.einstellungen.setdefault(key, default)

        self.configure_logging(app_state)

        logger.info("Log-Level beim Start: %s", app_state.log_level)
        logger.info(
            "Daten 48h Speicherung: %s",
            app_state.einstellungen.get("aktuell_aktiv"),
        )

        try:
            app_state.zugang = lade_zugang(STANDARD_ZUGANG)
        except Exception:
            logger.exception(
                "[Fehler beim Laden der Zugangsdaten] "
                "Standardwerte werden verwendet."
            )
            app_state.zugang = STANDARD_ZUGANG.copy()

        for key, default in STANDARD_ZUGANG.items():
            app_state.zugang.setdefault(key, default)

        app_state.growatt = GrowattSessionManager(
            app_state.zugang.get("username", ""),
            app_state.zugang.get("password", ""),
            app_state.zugang.get("deviceSn", ""),
            app_state.zugang.get("token", ""),
            app_state=app_state,
        )

    async def close_network_resources(
        self, app_state: AppState
    ) -> bool:
        """Schließt Netzwerkverbindungen beim Herunterfahren."""
        cleanup_succeeded = True

        manager = getattr(app_state, "_dose_manager", None)
        if manager is not None:
            if not await manager.shutdown():
                cleanup_succeeded = False
                logger.warning(
                    "Dose konnte beim Shutdown nicht sicher "
                    "ausgeschaltet werden."
                )

        growatt = getattr(app_state, "growatt", None)
        if growatt:
            try:
                await growatt.close()
            except Exception:
                cleanup_succeeded = False
                logger.exception("Growatt schließen fehlgeschlagen.")

        for attr_name in dir(app_state):
            if "session" not in attr_name.lower():
                continue

            session = getattr(app_state, attr_name, None)
            if (
                session
                and hasattr(session, "close")
                and not getattr(session, "closed", True)
            ):
                logger.info("Schließe Session: %s", attr_name)
                try:
                    await session.close()
                except Exception:
                    cleanup_succeeded = False
                    logger.exception(
                        "Fehler beim Schließen von %s", attr_name
                    )

        return cleanup_succeeded

    def register(self, app: Quart) -> None:
        """Registriert Start- und Shutdown-Abläufe bei Quart."""

        @app.before_serving
        async def init_daten() -> None:
            app_state = app.extensions["app_state"]

            try:
                self.load_configuration(app_state)

                if not (
                    os.environ.get("QUART_SECRET_KEY")
                    or os.environ.get("SECRET_KEY")
                ):
                    logger.warning(
                        "QUART_SECRET_KEY nicht gesetzt - "
                        "verwende temporären Fallback-Wert."
                    )

                logger.info("Starte Hintergrund-Task (einmalig).")
                app_state.is_shutting_down = False
                await mache_session(app_state, "session_push", timeout=10)

                await app_state.growatt.init_session()
                astro_werte(app_state)
                get_nachtzeten(app_state)
                await lade_aktuell_csv(app_state)

                app_state.aktuell_letztes_speichern = time.monotonic()
                runner = get_app_runner(app_state)

                async def safe_background_task() -> None:
                    async with app.app_context():
                        while True:
                            try:
                                await runner.wiederholte_takt()
                            except Exception:
                                logger.exception(
                                    "[Hintergrundfehler_init]"
                                )

                            await asyncio.sleep(
                                app_state.einstellungen.get(
                                    "intervall_takt", 5
                                )
                            )

                app.add_background_task(safe_background_task)
                logger.info(
                    "[Startup] Initialisierung & Hintergrund-Task laufen."
                )

            except BaseException:
                logger.exception(
                    "[Startup] Initialisierung fehlgeschlagen."
                )
                await self.close_network_resources(app_state)
                raise

        @app.after_serving
        async def shutdown() -> None:
            app_state = app.extensions["app_state"]

            if getattr(app_state, "is_shutting_down", False):
                return

            app_state.is_shutting_down = True
            logger.info("System-Shutdown eingeleitet.")
            shutdown_succeeded = True

            try:
                await pruefe_48st(app_state, 0)
            except Exception:
                shutdown_succeeded = False
                logger.exception("Fehler beim Speichern der 48h-Daten.")

            logger.info("Schließe Netzwerk-Sessions...")

            if not await self.close_network_resources(app_state):
                shutdown_succeeded = False

            if shutdown_succeeded:
                logger.info("Shutdown erfolgreich beendet.")
            else:
                logger.error(
                    "Shutdown beendet, aber nicht alle Schritte "
                    "waren erfolgreich."
                )


# Kompatibilität für bisherige Aufrufer
def _configure_logging(app_state: AppState) -> None:
    LifecycleManager().configure_logging(app_state)


def _load_configuration(app_state: AppState) -> None:
    LifecycleManager().load_configuration(app_state)


async def _close_network_resources(app_state: AppState) -> bool:
    return await LifecycleManager().close_network_resources(app_state)


def register_lifecycle(app: Quart) -> None:
    """Kompatibilität für bestehende Aufrufer."""
    LifecycleManager().register(app)
