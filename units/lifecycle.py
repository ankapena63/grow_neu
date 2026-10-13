import asyncio
import logging
import os
import time

from quart import Quart

from units.config import STANDARD_EINSTELLUNGEN, STANDARD_ZUGANG
from units.calculations import SonnenManager
from units.configuration import EinstellungenManager, mache_session
from units.runner import get_app_runner
from units.unit_battery import GrowattSessionManager
from units.logg import LogManager, setup_logging
from units.state import AppState

logger = logging.getLogger(__name__)


class LifecycleManager:
    """Kapselt Konfiguration, Start und geordnetes Beenden."""

    def configure_logging(self, app_state: AppState) -> None:
        """Richtet das Logging anhand der Einstellungen ein."""
        app_state.log_level = LogManager.normalize_level(
            app_state.einstellungen.get("log_level", "INFO")
        )
        log_level = LogManager.LEVELS[app_state.log_level]

        setup_logging(log_level)

        logging.getLogger("tinytuya").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.ERROR)
        logging.getLogger("hypercorn").setLevel(logging.WARNING)
        logging.getLogger("quart").setLevel(logging.WARNING)

    def load_configuration(self, app_state: AppState) -> None:
        """Lädt Einstellungen, Zugangsdaten und Growatt-Zugang."""
        try:
            app_state.einstellungen = EinstellungenManager.lade_einstellungen(
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
            app_state.zugang = EinstellungenManager.lade_zugang(STANDARD_ZUGANG)
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
                SonnenManager.astro_werte(app_state)
                SonnenManager.get_nachtzeten(app_state)

                # Der Runner besitzt den gemeinsamen HistoryManager.
                runner = get_app_runner(app_state)
                await runner.history_manager.lade_aktuell_csv()

                app_state.aktuell_letztes_speichern = time.monotonic()

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
                await get_app_runner(app_state).backup_manager.pruefe_48st(0)
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
