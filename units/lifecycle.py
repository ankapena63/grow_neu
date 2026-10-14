import asyncio
import logging
import os
import time

from quart import Quart

from units.config import STANDARD_EINSTELLUNGEN, STANDARD_ZUGANG
from units.calculations import SonnenManager
from units.configuration import EinstellungenManager, SessionManager
from units.runner import AppRunner
from units.history import HistoryManager
from units.device_factory import DeviceFactory
from units.logg import LogManager
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

        LogManager.setup(log_level)

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

        DeviceFactory.initialisiere_growatt(app_state)

    async def close_network_resources(
        self, app_state: AppState
    ) -> bool:
        """Schließt alle Netzwerkressourcen auch bei Teilfehlern."""
        cleanup_succeeded = True

        # Jede Ressource wird unabhängig geschlossen. Ein Fehler an der
        # Dose darf weder Growatt noch die gemeinsamen HTTP-Sessions offenlassen.
        manager = getattr(app_state, "_dose_manager", None)
        if manager is not None:
            try:
                if not await manager.shutdown():
                    cleanup_succeeded = False
                    logger.warning(
                        "Dose konnte beim Shutdown nicht sicher "
                        "ausgeschaltet werden."
                    )
            except Exception:
                cleanup_succeeded = False
                logger.exception("Dose-Shutdown fehlgeschlagen.")

        growatt = getattr(app_state, "growatt", None)
        if growatt is not None:
            try:
                await growatt.close()
            except Exception:
                cleanup_succeeded = False
                logger.exception("Growatt schließen fehlgeschlagen.")

        try:
            session_manager = SessionManager.fuer(app_state)
            if not await session_manager.schliesse_alle():
                cleanup_succeeded = False
        except Exception:
            cleanup_succeeded = False
            logger.exception("HTTP-Sessions schließen fehlgeschlagen.")

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
                session_manager = SessionManager.fuer(app_state)
                await session_manager.erstelle("session_push", timeout=10)

                await app_state.growatt.init_session()
                SonnenManager.astro_werte(app_state)
                SonnenManager.get_nachtzeten(app_state)

                # Historie unabhängig vom Hintergrund-Runner laden.
                await HistoryManager.fuer(app_state).lade_aktuell_csv()
                runner = AppRunner.fuer(app_state)

                app_state.aktuell_letztes_speichern = time.monotonic()

                async def safe_background_task() -> None:
                    async with app.app_context():
                        while not app_state.is_shutting_down:
                            try:
                                await runner.wiederholte_takt()
                            except Exception:
                                logger.exception("[Hintergrundfehler_init]")

                            # Ungültige oder versehentlich sehr kleine
                            # Konfigurationen dürfen keine enge Endlosschleife
                            # erzeugen oder den Hintergrund-Task beenden.
                            try:
                                intervall = float(
                                    app_state.einstellungen.get(
                                        "intervall_takt", 5
                                    )
                                )
                            except (TypeError, ValueError):
                                intervall = 5.0

                            if not 0.1 <= intervall <= 3600:
                                logger.warning(
                                    "Ungültiges intervall_takt=%r; "
                                    "verwende 5 Sekunden.",
                                    app_state.einstellungen.get(
                                        "intervall_takt"
                                    ),
                                )
                                intervall = 5.0

                            # Beim Shutdown nicht bis zum Ende eines langen Takts warten.
                            shutdown_event = app.extensions.get("server_shutdown_event")
                            if shutdown_event is None:
                                await asyncio.sleep(intervall)
                            else:
                                try:
                                    await asyncio.wait_for(
                                        shutdown_event.wait(),
                                        timeout=intervall,
                                    )
                                except asyncio.TimeoutError:
                                    pass

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
                await HistoryManager.fuer(app_state).pruefe_48st(0)
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
