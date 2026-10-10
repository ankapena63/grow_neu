import asyncio
from datetime import datetime
import logging
import tinytuya
from quart import Blueprint, current_app, request
from units.configuration import speichere_einstellungen
from units.calculations import status_aktualisieren, zeitstempel
from units.history import schreibe_in_roh
from units.state import AppState#, DoseDevice
from units.unit_dose import DoseDevice

logger = logging.getLogger(__name__)

def _dose_device(app_state: AppState) -> DoseDevice:
    if app_state.dose_device is None:
        raise RuntimeError("Das Tuya-Dosengerät wurde nicht initialisiert.")
    return app_state.dose_device

async def async_tuya_status(app_state: AppState):
    return await asyncio.to_thread(_dose_device(app_state).status)

async def async_tuya_on(app_state: AppState):
    return await asyncio.to_thread(_dose_device(app_state).turn_on)

async def async_tuya_off(app_state: AppState):
    return await asyncio.to_thread(_dose_device(app_state).turn_off)

async def dose_tuya_status(app_state: AppState):
    try:
        data = await async_tuya_status(app_state)
        schreibe_in_roh(app_state, "dose", data)
        if not data or "dps" not in data:
            logger.error("Dose nicht erreichbar")
            return None
        is_on = data["dps"].get("1")
        app_state.dose_watt = float(data.get("dps", {}).get("22", 0)) / 10
        takt = app_state.einstellungen.get("takt_dose", 300)
        app_state.alle_daten["dose"]["zeit_meine"] = zeitstempel()
        app_state.alle_daten["dose"]["takt_dose"] = takt
        status_aktualisieren(app_state, "dose", takt)
        return is_on
    except Exception:
        logger.exception("❌ Dose Fehler beim Status-Abruf:")
        return None

async def dose_tuya(app_state: AppState) -> None:
    if app_state.dose_laeuft:
        return
    app_state.dose_laeuft = True
    try:
        is_on = await dose_tuya_status(app_state)
        app_state.dose_relay_state = is_on
        if is_on is None:
            return

        akku_zeit_str = app_state.alle_daten.get("akku", {}).get("zeit_Noah")
        diff_sekunden = 9999
        if akku_zeit_str:
            try:
                noah_dt = datetime.strptime( akku_zeit_str, "%Y-%m-%d %H:%M:%S" )
                diff_sekunden = (datetime.now() - noah_dt).total_seconds()
            except Exception:
                logger.exception("❌Zeit-Fehler:")
        else:
            logger.warning("⚠️Keine zeit_Noah gefunden")
        if diff_sekunden == 9999:
            logger.info("⚠️ [Dose]- Not keine  Akku-Daten")
            return
        if diff_sekunden > 1200:
            if is_on:
                logger.info(
                    "⚠️ Not-Aus: Akku-Daten sind %s Sek. alt!",
                    int(diff_sekunden),
                )
                await relay_off(app_state)
            return
        if app_state.dose_mode != "auto":
            return
        temp = app_state.temperature
        t_start = app_state.einstellungen.get("dose_t_start", 32)
        t_stop = app_state.einstellungen.get("dose_t_stop", 28)
        if temp >= t_start and not is_on:
            await relay_on(app_state)
        elif temp <= t_stop and is_on:
            await relay_off(app_state)
    except Exception:
        logger.exception("❌Dose Fehler:")
    finally:
        app_state.dose_laeuft = False

async def relay_on(app_state: AppState) -> None:
    if app_state.dose_relay_state is True:
        logger.info("Dose ist An")
        return
    try:
        await async_tuya_on(app_state)
        data = await async_tuya_status(app_state)
        if data and "dps" in data:
            is_on = data["dps"].get("1")
            if is_on is True:
                logger.info("Dose An ✅")
                app_state.dose_watt = float(data.get("dps", {}).get("22", 0)) / 10
                app_state.dose_relay_state = True
            else:
                logger.error("❌ Schaltvorgang fehlgeschlagen")
                app_state.dose_relay_state = is_on
        else:
            logger.error("❌Keine Antwort – Dose offline")
            app_state.dose_relay_state = None
    except Exception:
        logger.exception("❌Fehler beim Einschalten:")
        app_state.dose_relay_state = None

async def relay_off(app_state: AppState) -> None:
    if app_state.dose_relay_state is False:
        return
    try:
        await async_tuya_off(app_state)
        data = await async_tuya_status(app_state)
        if data and "dps" in data:
            is_on = data["dps"].get("1")
            app_state.dose_relay_state = is_on
            if is_on is False:
                logger.info("✅Dose erfolgreich AUS")
            else:
                logger.warning("Dose ist noch AN – Schaltvorgang fehlgeschlagen")
        else:
            logger.error("❌Keine Antwort – Dose offline")
            app_state.dose_relay_state = None
    except Exception:
        logger.exception("❌Fehler beim Ausschalten:")
        app_state.dose_relay_state = None

async def shutdown_dose(app_state: AppState) -> bool:
    try:
        await async_tuya_off(app_state)
        logger.info("✅Not-Aus: Dose ausgeschaltet.")
        return True
    except Exception:
        logger.exception("❌Not-Aus: Dose konnte nicht ausgeschaltet werden.")
        return False

def create_dose_device() -> DoseDevice:
    device = tinytuya.OutletDevice(
        "bfe769408c34e0dd06iuai",
        "192.168.178.41",
        "+k?nQL;':Lei5F)g",
    )
    device.set_version(3.4)
    device.set_socketTimeout(2)
    device.set_socketRetryLimit(1)
    return device

bp = Blueprint("dose", __name__, url_prefix="/dose")

def _app_state() -> AppState:
    return current_app.extensions["app_state"]

@bp.route("/set_mode", methods=["POST"])
async def set_mode():
    data = await request.form
    mode = data.get("mode", "manual")
    _app_state().dose_mode = mode
    return "", 204

@bp.route("/manual", methods=["POST"])
async def manual():
    app_state = _app_state()
    form_data = await request.form
    if form_data.get("action") == "on":
        await relay_on(app_state)
    else:
        await relay_off(app_state)
    return "", 204

@bp.route("/set_temps", methods=["POST"])
async def set_temps():
    app_state = _app_state()
    data = await request.form
    try:
        start = int(data.get("start", 32))
        stop = int(data.get("stop", 28))
    except ValueError:
        return "Ungültige Werte", 400
    if not 20 <= start <= 45:
        return "Start muss zwischen 20 und 45°C liegen", 400
    if stop > start - 1:
        return "Stop muss mindestens 1°C kleiner als Start sein", 400
    if stop < 0:
        return "Stop darf nicht negativ sein", 400

    app_state.einstellungen["dose_t_start"] = start
    app_state.einstellungen["dose_t_stop"] = stop
    await speichere_einstellungen(app_state, app_state.einstellungen)
    await dose_tuya(app_state)
    return "", 204
