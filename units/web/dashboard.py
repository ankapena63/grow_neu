"""Dashboard routes."""
from . import routes, _app_state
from quart import redirect, render_template, request
from units.unit_alle.calculations import (
    get_heute_werte,
    get_jahres_werte,
    get_monats_werte,
)
from units.unit_alle.configuration import (
    load_tageswerte,
    run_sshd,
    speichere_einstellungen,
    start_sshd,
    stop_sshd,
)
from units.unit_alle.calculations import haus_verbrauch_get
from units.unit_alle.runner import rechne_dazu
from units.state import AppState
import logging
import time

def get_web_daten(app_state: AppState) -> dict:
    return {
        "dazu": app_state.dazu,
        "haus_verbrauch": haus_verbrauch_get(app_state),
        "stunden_bis_nacht": app_state.stunden_bis_nacht,
        "brauche_watt": app_state.brauche_watt,
        "pro_stunde": app_state.pro_stunde,
        "akku_sanft_zeit": app_state.akku_sanft_zeit,
        "dazu_intervall": app_state.dazu_intervall,
        "dazu_sanft_soc": app_state.dazu_sanft_soc,
        "sonnenaufgang": app_state.sonnenaufgang,
        "sonnenuntergang": app_state.sonnenuntergang,
        "tageslange": app_state.tageslange,
        "startnacht": app_state.startnacht,
        "endnacht": app_state.endnacht,
        "nachtzeit": app_state.nachtzeit,
        "dose_mode": app_state.dose_mode,
        "dose_relay_state": app_state.dose_relay_state,
        "dose_watt": app_state.dose_watt,
        "solax_l_mittelwert": app_state.solax_l_mittelwert,
        "ppv_mittelwert": app_state.ppv_mittelwert,
        "temperature": app_state.temperature,
    }

@routes.route("/tageswerte")
async def tageswerte():
    state: AppState = _app_state()
    return await render_template(
        'tageswerte.html',
        web           = get_web_daten(_app_state()),
        einstellungen = state.einstellungen,
        datei_daten0  = load_tageswerte("tageswerte0.csv"),
        headers       =["Tag", "E🏠", "V🏠", "HMS", "🔋", "Sol"]
    )

@routes.route("/")
async def dashboard():
    state: AppState = _app_state()
    state.einstellungen["server_sshd"] = run_sshd(_app_state())
    return await render_template(
        "dashboard.html",
        daten          = state.alle_daten,
        tag_daten      = get_heute_werte(state.alle_daten,state.einstellungen),
        monat_daten    = get_monats_werte(state.alle_daten,state.einstellungen),
        jahr_daten     = get_jahres_werte(state.alle_daten,state.einstellungen),
        einstellungen  = state.einstellungen, 
        version        = state.version,
        web            = get_web_daten(_app_state()),
        solax_local    = state.solax_local
    )

@routes.route("/server_sshd", methods=["POST"])
async def server_sshd():
    if run_sshd(_app_state()):
        stop_sshd(_app_state())
    else:
        start_sshd(_app_state())
    return redirect("/")

@routes.route("/kochen_start", methods=["POST"])
async def kochen_start():
    state: AppState = _app_state()
    data = await request.get_json()
    try:  
        interval       = int(data.get("kochen_zeit", 0)) # Minuten
        kochen_soc_min = int(data.get("kochen_soc_min", 30)) 
        kochen_wert    = int(data.get("kochen_wert", 1400)) 
    except (TypeError, ValueError): 
        return {  
            "ok": False, 
            "fehler": "Ungültige Koch-Einstellungen" }
    # Grenzen 
    kochen_soc_min = max(30, min(90, kochen_soc_min)) 
    kochen_wert = max(100, min(3000, kochen_wert))
    akku_soc = state.soc
# PRÜFEN
    if interval <= 0:
        state.kochen = False
        return {
            "ok": False,
            "fehler": "Zeit soll nich 0 sein"
        }
    if akku_soc <= kochen_soc_min:
        state.kochen= False
        state.kochen_zeit = 0.0 
        state.kochen_end = 0.0
        return {
            "ok": False,
           "fehler": f"Akku SOC zu klein: {akku_soc:.0f}% " 
                     f"(mindestens {kochen_soc_min}%)"
        }
    # SPEICHERN
    alt_soc_min = state.einstellungen.get("kochen_soc_min", 30)
    alt_wert    = state.einstellungen.get("kochen_wert", 1400)
# Neue Werte setzen
    state.einstellungen["kochen_soc_min"] = kochen_soc_min
    state.einstellungen["kochen_wert"] = kochen_wert
# Nur speichern, wenn sich etwas geändert hat
    if (alt_soc_min != kochen_soc_min or alt_wert != kochen_wert):
       await speichere_einstellungen(_app_state(), state.einstellungen)
    state.kochen       = True
    logging.info("KOCHEN An: für: %s min %s Watt",interval,kochen_wert)
    state.kochen_zeit  = interval
    state.kochen_end   = (time.monotonic() + interval * 60)
    await rechne_dazu(_app_state())
    return { 
        "ok": True,
        "kochen": True, 
        "kochen_zeit": state.kochen_zeit, 
        "kochen_end": state.kochen_end, 
        "kochen_soc_min": state.einstellungen["kochen_soc_min"], 
        "kochen_wert": state.einstellungen["kochen_wert"] }

@routes.route("/kochen_stop", methods=["POST"])
async def kochen_stop():
    state: AppState = _app_state()
    state.kochen= False
    state.kochen_zeit = 0.0
    state.kochen_end =0.0
    await rechne_dazu(_app_state())
    logging.info("KOCHEN Ausgeschaltet")
    return {"ok": True,
            "kochen": False}

@routes.route("/dia")
async def diagramm():
    return await render_template("diagramm.html")

@routes.route("/aktuell")
async def aktuell():
    return await render_template("aktuell.html")

@routes.route("/stat")
async def stat():
    return await render_template("stat.html")

@routes.get("/log")
async def log_seite():
    return await render_template("log.html")
