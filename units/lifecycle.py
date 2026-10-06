import asyncio
import logging
import os
import time
import aiohttp
from quart import Quart
from units.config import STANDARD_EINSTELLUNGEN, STANDARD_ZUGANG
from units.unit_dose import shutdown_dose
from units.unit_alle.calculations import astro_werte, get_nachtzeten
from units.unit_alle.configuration import (
    lade_einstellungen,
    lade_zugang,
)
from units.unit_alle.history import lade_aktuell_csv
from units.unit_alle.runner import pruefe_48st, wiederholte_takt
from units.unit_battery import GrowattSessionManager
from units.logg import setup_logging
from units.state import AppState

logger = logging.getLogger(__name__)

def _configure_logging(app_state: AppState) -> None:
    levels = {
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
    }
    app_state.log_level = app_state.einstellungen.get("log_level", "INFO").upper()
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

def _load_configuration(app_state: AppState) -> None:
    try:
        app_state.einstellungen = lade_einstellungen(STANDARD_EINSTELLUNGEN)
    except Exception:
        logger.exception(
            "[Fehler beim Laden der Einstellungen] "
            "Standardwerte werden verwendet."
        )
        app_state.einstellungen = STANDARD_EINSTELLUNGEN.copy()
    for key, default in STANDARD_EINSTELLUNGEN.items():
        app_state.einstellungen.setdefault(key, default)

    _configure_logging(app_state)
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

async def _close_network_resources(app_state: AppState) -> bool:
    cleanup_succeeded = True
    if not await shutdown_dose(app_state):
        cleanup_succeeded = False

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
                logger.exception("Fehler beim Schließen von %s", attr_name)
    return cleanup_succeeded

def register_lifecycle(app: Quart) -> None:
    @app.before_serving
    async def init_daten() -> None:
        app_state = app.extensions["app_state"]
        try:
            _load_configuration(app_state)
            if not (
                os.environ.get("QUART_SECRET_KEY")
                or os.environ.get("SECRET_KEY")
            ):
                logger.warning(
                    "QUART_SECRET_KEY nicht gesetzt; "
                    "verwende temporären Fallback-Wert."
                )
            logger.info("Starte Hintergrund-Task (einmalig).")
            app_state.is_shutting_down = False
            app_state.session_push = aiohttp.ClientSession()
            await app_state.growatt.init_session()
            astro_werte(app_state)
            get_nachtzeten(app_state)
            await lade_aktuell_csv(app_state)
            app_state.aktuell_letztes_speichern = time.monotonic()
            async def safe_background_task() -> None:
                async with app.app_context():
                    while True:
                        try:
                            await wiederholte_takt(app_state)
                        except Exception:
                            logger.exception("[Hintergrundfehler_init]")
                        await asyncio.sleep(
                            app_state.einstellungen.get("intervall_takt", 5)
                        )
            app.add_background_task(safe_background_task)
            logger.info("[Startup] Initialisierung & Hintergrund-Task laufen.")
        except BaseException:
            logger.exception("[Startup] Initialisierung fehlgeschlagen.")
            await _close_network_resources(app_state)
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
        if not await _close_network_resources(app_state):
            shutdown_succeeded = False
        if shutdown_succeeded:
            logger.info("Shutdown erfolgreich beendet.")
        else:
            logger.error(
                "Shutdown beendet, aber nicht alle Schritte waren erfolgreich."
            )
