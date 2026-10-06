"""Api routes."""
from . import routes, _app_state
from datetime import date, datetime
from quart import jsonify, request
from units.unit_alle.calculations import (
    gereate_status,
    get_heute_werte,
    get_jahres_werte,
    get_monats_werte,
)
from units.unit_alle.configuration import speichere_einstellungen
from units.unit_alle.history import lese_tageswerte0
from units.web.dashboard import get_web_daten
from units.logg import log_buffer
from units.state import AppState
import logging
import time
import logging
logger = logging.getLogger(__name__)

@routes.route("/api/daten")
async def api_daten():
    state: AppState = _app_state()
    state.last_activity = time.monotonic()
    kochen_web ={
               "kochen": state.kochen,
               "kochen_zeit": state.kochen_zeit,
               "kochen_end": state.kochen_end,
               "kochen_soc_min": state.einstellungen.get("kochen_soc_min", 30),
               "kochen_wert": state.einstellungen.get("kochen_wert", 1400)}

    return {"daten":state.alle_daten, 
            "tag_daten"     : get_heute_werte(state.alle_daten,state.einstellungen),
            "monat_daten"   : get_monats_werte(state.alle_daten,state.einstellungen),
            "jahr_daten"    : get_jahres_werte(state.alle_daten,state.einstellungen),
            "status"        : gereate_status(state.status_html),
            "solax_local"   : state.solax_local,
            "web"           : get_web_daten(_app_state()),
            "akku_login"    : state.growatt.akku_login_daten,
            "kochen"        : kochen_web ,
            "einstellungen" : state.einstellungen}

@routes.route("/strom", methods=["GET"])
async def get_strom():
    state: AppState = _app_state()
    daten_strom = state.alle_daten.get("strom") or {}

    if not daten_strom:
        return jsonify({"error": "Keine gültigen Stromdaten verfügbar"}), 500
    return jsonify(daten_strom)

@routes.route("/akku_cloud", methods=["GET"])
def get_akku_cloud():
    state: AppState = _app_state()
    return jsonify({
         "Seite"       :  "Akku Cloud",
         "meine_daten" :  state.alle_daten.get("akku", {}), 
         "akku_login"  :  state.roh.get("akku_login",  {}),
         "akku_status" :  state.roh.get("akku_status", {}),
         "akku_token"  :  state.roh.get("akku_token",  {})
         })

@routes.route("/hms", methods=["GET"])
def get_hms_800():
    state: AppState = _app_state()
    return jsonify({
         "Seite"       :  "HNS-800-2T",
         "meine_daten" :  state.alle_daten.get("hms", {}),
         "server_roh"  :  state.roh.get("hms", {})
    })

@routes.route("/solax_cloud", methods=["GET"])
async def get_sol_cloud():
    state: AppState = _app_state()
    return jsonify({
         "Seite": "Solax Cloud",
         "meine_daten" : state.alle_daten.get("solax", {}),
         "server_roh" : state.roh.get("solax_c", {})
         })

@routes.route("/solax_local", methods=["GET"])
async def get_local():
    state: AppState = _app_state()
    state.solax_local = await state.solax.abfrage_local(
        state.einstellungen.get("takt_solax_l", 15)
    )
    return jsonify({
         "Seite"       : "Solax Local",
         "meine_daten" :  state.solax_local,
         "server_roh"  :  state.roh.get("solax_l", {})
         })

@routes.route("/parameter", methods=["GET"])
async def get_parameter():
    state: AppState = _app_state()
    return jsonify(state.einstellungen)

@routes.route("/parameter_zugang", methods=["GET"])
async def get_parameter_zugang():
    state: AppState = _app_state()
    return jsonify({
        "Seite": "parameter_zugang",
        "web_daten" : get_web_daten(_app_state()),
         "zugang"     :   state.zugang})

@routes.route("/status", methods=["GET"])
async def get_latest_status():
    state: AppState = _app_state()
    if not state.alle_daten:
        return jsonify({"error": "Keine Daten vorhanden"}), 500
    return jsonify({
        "alle":state.alle_daten,
        "status_html": state.status_html,
        "Takte"     : state.takte
        })

@routes.route("/tages", methods=["GET"])
async def get_tages():
    state: AppState = _app_state()
    return jsonify(get_heute_werte(state.alle_daten,state.einstellungen),
                   get_monats_werte(state.alle_daten,state.einstellungen),
                   get_jahres_werte(state.alle_daten,state.einstellungen)
    )

@routes.route("/roh", methods=["GET"])
def roh():
    state: AppState = _app_state()
    return jsonify(state.roh)

@routes.route("/api/diagramm")
async def api_diagramm():
    jahr = int(request.args.get("jahr", date.today().year))
    monat = int(request.args.get("monat", date.today().month))
    modus = request.args.get("modus", "monat")
    tageswerte = lese_tageswerte0()
    # ==========================================================
    # JAHRESANSICHT
    # ==========================================================
    if modus == "jahr":
        monatswerte = []
        for m in range(1, 13):
            werte = []
            for wert in tageswerte:
                datum = datetime.strptime(
                    wert["datum"],
                    "%d.%m.%y"
                ).date()
                if datum.year == jahr and datum.month == m:
                    werte.append(wert)
            einspeise = round(sum(wert["einspeise"] for wert in werte), 2)
            gesamt = round(sum(wert["gesamt"] for wert in werte),2 )
            hms = round(sum(wert["hms"] for wert in werte), 2)
            growatt = round(sum(wert["growatt"] for wert in werte),2)
            solax = round(sum(wert["solax"] for wert in werte), 2)
            # ==================================================
            # SolarVERBRAUCH
            # ==================================================
            solarverbrauch = round( hms + solax - einspeise, 2)
            monatswerte.append({
                "monat": m,
                "einspeise": einspeise,
                "gesamt": gesamt,
                "hms": hms,
                "growatt": growatt,
                "solax": solax,
                "solarverbrauch": solarverbrauch
            })
        monatsnamen = [
            "Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug","Sep", "Okt", "Nov", "Dez"
        ]
        return jsonify({
            "modus": "jahr",
            "jahr": jahr,
            "labels": monatsnamen,
            "einspeise": [ wert["einspeise"]for wert in monatswerte ],
            "gesamt": [wert["gesamt"]for wert in monatswerte ],
            "hms": [wert["hms"] for wert in monatswerte],
            "growatt": [ wert["growatt"]  for wert in monatswerte],
            "solax": [wert["solax"]for wert in monatswerte ],
            "solarverbrauch": [wert["solarverbrauch"] for wert in monatswerte ],
            "summen": {
                "einspeise": round(
                    sum(wert["einspeise"] for wert in monatswerte),2),
                "gesamt": round(
                    sum(wert["gesamt"] for wert in monatswerte),2 ),
                "hms": round(
                    sum(wert["hms"] for wert in monatswerte),2 ),
                "growatt": round(
                    sum(wert["growatt"] for wert in monatswerte),2 ),
                "solax": round(
                    sum(wert["solax"] for wert in monatswerte), 2),
                "solarverbrauch": round(
                    sum(wert["solarverbrauch"] for wert in monatswerte),2)
            }
        })
    # ==========================================================
    # MONATSANSICHT
    # ==========================================================
    monat_werte = []
    for wert in tageswerte:
        datum = datetime.strptime(
            wert["datum"],
            "%d.%m.%y"
        ).date()
        if datum.year == jahr and datum.month == monat:
            monat_werte.append(wert)
    logger.info(
    "[DIAGRAMM] Monat %02d.%s: %s Tage",
    monat, jahr, len(monat_werte)
    )
    # ==========================================================
    # SolarVERBRAUCH PRO TAG BERECHNEN
    # ==========================================================
    solarverbrauch = [
        round( wert["hms"]+ wert["solax"] - wert["einspeise"],2)
        for wert in monat_werte
    ]
    return jsonify({
        "modus": "monat",
        "jahr": jahr,
        "monat": monat,
        "labels": [ wert["datum"]for wert in monat_werte],
        "einspeise": [ wert["einspeise"] for wert in monat_werte],
        "gesamt": [ wert["gesamt"] for wert in monat_werte ],
        "hms": [ wert["hms"] for wert in monat_werte ],
        "growatt": [ wert["growatt"]for wert in monat_werte],
        "solax": [ wert["solax"]for wert in monat_werte],
        "solarverbrauch": solarverbrauch,
        "summen": {
            "einspeise": round(sum(wert["einspeise"] for wert in monat_werte),2),
            "gesamt": round( sum(wert["gesamt"] for wert in monat_werte), 2 ),
            "hms": round(sum(wert["hms"] for wert in monat_werte),2),
            "growatt":round(sum(wert["growatt"] for wert in monat_werte),  2  ),
            "solax": round(sum(wert["solax"] for wert in monat_werte),  2 ),
            "solarverbrauch": round(sum(solarverbrauch),2 )
        }
    })

@routes.route("/api/aktuell")
async def api_aktuell():
    state: AppState = _app_state()
    daten = {}
    for geraet, werte in state.aktuell_werte.items():
        daten[geraet] = [
            {
                "zeit": datetime.fromtimestamp(zeit).isoformat(
                    timespec="seconds"
                ),
                "wert": wert
            }
            for zeit, wert in werte
        ]
    return jsonify(daten)

@routes.route("/api/stat")
async def api_status():
    state: AppState = _app_state()
    #state.last_activity = time.monotonic()
    return jsonify(state.status_html)

@routes.get("/api/log")
async def api_log():
    return {
        "log": list(log_buffer),
        "level": logging.getLogger().getEffectiveLevel()
    }

@routes.post("/api/log_level")
async def api_log_level():
    state: AppState = _app_state()
    data = await request.get_json()
    level = data.get("level", "INFO").upper()
    levels = {
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG
    }
    if level not in levels:
        level = "INFO"
    log_level = levels[level]
    # Root-Logger ändern
    root = logging.getLogger()
    root.setLevel(log_level)
    # ALLE Handler ebenfalls ändern
    for handler in root.handlers:
        handler.setLevel(log_level)
    state.log_level = level
    state.einstellungen["log_level"] = level
    await speichere_einstellungen(_app_state(), state.einstellungen)
    # Meldung NACH dem Umschalten erzeugen
    if level == "ERROR":
        logger.error("Log-Level geändert auf ERROR")
    elif level == "WARNING":
        logger.warning("Log-Level geändert auf WARNING")
    elif level == "INFO":
        logger.info("Log-Level geändert auf INFO")
    elif level == "DEBUG":
        logger.debug("Log-Level geändert auf DEBUG")
    return {
        "ok": True,
        "level": level
    }
