"""Calculations services."""
from astral import LocationInfo
from zoneinfo import ZoneInfo
from datetime import datetime, date
from astral.sun import sun
import time

def zeitstempel():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def mittelwert_get(wert,werte):
    if wert is not None:
        werte.append(wert)
    if not werte:
        return 0  # oder ein sinnvoller Standardwert wie 100
    return sum(werte) / len(werte)

def astro_werte(app_state):
    # Richtige Zeitzone setzen!
    aachen = LocationInfo(
        name="Aachen",
        region="Germany",
        timezone="Europe/Berlin",
        latitude=50.7753,
        longitude=6.0839
    )
    s = sun(aachen.observer, date=date.today(), tzinfo=ZoneInfo("Europe/Berlin"))
    sunrise = s["sunrise"]
    sunset = s["sunset"]
    app_state.sonnenaufgang    = sunrise.strftime("%H:%M:%S")
    app_state.sonnenuntergang  = sunset.strftime("%H:%M:%S")
    app_state.tageslange       = str((sunset - sunrise)).split('.')[0]
    return

def get_heute_werte(daten,einst):
    werte = {}
    werte["datum"] = date.today().strftime("%d.%m.%Y")  #date.today().isoformat()
 
    werte["tag_t"] = date.today().timetuple().tm_yday   #tag
    if "strom" in daten:
        if "Einspeise" in daten["strom"]:
            werte["einspeise_t"] = round(max(0, daten["strom"]["Einspeise"] - einst.get("einspeise_0", 0)),2)
        if "Gesamt" in daten["strom"]:
            werte["gesamt_t"] = round(max(0, daten["strom"]["Gesamt"] - einst.get("gesamt_0", 0)),3)
    if "hms" in daten:
        if "gesamt" in daten["hms"]:
            werte["hms_t"] =round(max(0, daten["hms"]["gesamt"] - einst.get("hms_0", 0)),3)
    if "akku" in daten: 
        if "eacTotal" in daten["akku"]:
            werte["growatt_t"] =round(max(0, daten["akku"]["eacTotal"] - einst.get("growatt_0", 0)),3)
    if "solax" in daten:
        if "gesamt" in daten["solax"]:
            werte["solax_t"] =round(max(0, daten["solax"]["gesamt"] - einst.get("solax_0", 0)),3)
    return werte

def get_monats_werte(daten, einst):
    werte = {}
    werte["monat"] = date.today().month
    werte["einspeise"] = round(
        max(0, daten.get("strom", {}).get("Einspeise", 0)
            - einst.get("einspeise_monat_0", 0)), 2)
    werte["gesamt"] = round(
        max(0, daten.get("strom", {}).get("Gesamt", 0)
            - einst.get("gesamt_monat_0", 0)), 2)
    werte["hms"] = round(
        max(0, daten.get("hms", {}).get("gesamt", 0)
            - einst.get("hms_monat_0", 0)), 2)
    werte["growatt"] = round(
        max(0, daten.get("akku", {}).get("eacTotal", 0)
            - einst.get("growatt_monat_0", 0)), 2)
    werte["solax"] = round(
        max(0, daten.get("solax", {}).get("gesamt", 0)
            - einst.get("solax_monat_0", 0)), 2)
    return werte

def get_jahres_werte(daten, einst):
    werte = {}
    werte["jahr"] = date.today().year
    werte["einspeise"] = round(
        max(0,
            daten.get("strom", {}).get("Einspeise", 0)
            - einst.get("einspeise_jahr_0", 0)),2)
    werte["gesamt"] = round(
        max( 0,
            daten.get("strom", {}).get("Gesamt", 0)
            - einst.get("gesamt_jahr_0", 0)),2)
    werte["hms"] = round(
        max(0,
            daten.get("hms", {}).get("gesamt", 0)
            - einst.get("hms_jahr_0", 0)),2)
    werte["growatt"] = round(
        max(0,
            daten.get("akku", {}).get("eacTotal", 0)
            - einst.get("growatt_jahr_0", 0)),2)
    werte["solax"] = round(
        max(0,
            daten.get("solax", {}).get("gesamt", 0)
            - einst.get("solax_jahr_0", 0)),2)
    return werte

def status_aktualisieren(app_state, geraet, takt):
    if geraet not in app_state.status_html:
        app_state.status_html[geraet] = {}
    app_state.status_html[geraet]["zeit_meine"] = zeitstempel()
    app_state.status_html[geraet]["takt"] = takt

def gereate_status(status_html):
    status ={}
    jetzt = time.time()
    for key, info in status_html.items():
        zeit = info.get("zeit_meine", 0)
        takt = info.get("takt", 10)
        if not zeit:
            status[key] = 0
            continue
        try:
            if isinstance(zeit, str):
                zeit = datetime.strptime(
                    zeit, "%Y-%m-%d %H:%M:%S"
                ).timestamp()
            diff = jetzt - zeit
            if diff < 0:
               diff = 0
        except (ValueError, TypeError):
            status[key] = 0
            continue
        if diff > takt*10:
            status[key] = 0
            continue
        if diff <= takt:
            status[key] = 1
        elif diff <= takt * 4:
            status[key] = 2
        else:
            status[key] = 3
    return status

def haus_verbrauch_get (app_state):
    solax = app_state.alle_daten.get("solax", {}).get("acpower", 0) or 0
    hms   = app_state.alle_daten.get("hms", {}).get("aktuell", 0) or 0
    strom = app_state.alle_daten.get("strom", {}).get("Actuel", 0) or 0
    return  round(solax + hms + strom)
