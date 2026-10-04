from units.state import AppState
from units.funkzii import (
  mittelwert_get,
  speichere_tageswerte,
  speichere_einstellungen,
  sende_vdazu_tasmota,
  sende_vdazu_smart,
  astro_werte,
  get_heute_werte,
  rotate_logs
  )
import time
from datetime import datetime, timedelta, date  # , timezone
from units.config import (
    FELDREIHENFOLGE
)
#from zoneinfo import ZoneInfo  # eingebaut in Python 3.9+
import logging

logger = logging.getLogger(__name__)

async def sende_dazu(app_state: AppState, wert):
    soc = app_state.soc
    if not(app_state.nachtzeit and app_state.einstellungen.get('nacht_nur_0_schalter', False)) :
        if app_state.kochen\
            and app_state.kochen_zeit>0\
            and soc > app_state.einstellungen.get("kochen_soc_min",30):
                wert += int(app_state.einstellungen.get("kochen_wert", 600))
    dazu_alt = app_state.dazu
    zeit_jetzt = time.monotonic()

    diff = abs(dazu_alt - wert)
    timeout = (zeit_jetzt - app_state.start_dazu_senden) > app_state.einstellungen.get("dazu_senden", 60)

    muss_senden = (
        diff > app_state.einstellungen.get("dazu_tolleranz", 0)
        or (timeout and wert != 0)
        or (wert == 0 and dazu_alt != 0)
    )
    if muss_senden:
       if app_state.einstellungen["abfrage_tasmota"]:
           antwort = await sende_vdazu_tasmota(app_state, wert)
           logger.debug("[SEND]  tasmota %s",antwort) 
       else:
           antwort = await sende_vdazu_smart(app_state, wert)
           logger.debug("[SEND]  smart %s" ,antwort) 

       if "error" not in antwort:
            # ERFOLG: Nur jetzt Werte im State aktualisieren
            app_state.dazu = wert
            app_state.start_dazu_senden = zeit_jetzt
            logger.info("[SEND dazu] ✅: %s ",wert)
            logger.debug("[SEND dazu] ✅: %s (Diff: %s, Timeout: %s)",wert, diff, timeout)
       else:
           # === KORREKTUR: Bei Fehler NICHT auf 0 setzen (Flutgefahr!). ===
            # Wir ziehen 45 Sekunden ab. Dadurch wird im nächsten Takt (in 5-15 Sek) 
            # erneut ein Sendeversuch gestartet, ohne die Hardware zu überlasten.           
            logger.error("[SEND] ❌ FEHLER: %s", antwort["error"])
            app_state.start_dazu_senden = zeit_jetzt - 45
    else:
        logger.info("[Dazu] %s in Toleranz/Zeit.", wert)
 
async def rechne_dazu(app_state: AppState):

    einst = app_state.einstellungen
    if app_state.nachtzeit or einst.get("nur_nulleinspeisung"):
        await sende_dazu(app_state, 0)
        logger.info("🌙 Nachtbetrieb oder Nulleinspeisung → dazu = 0")
        return
    akku = app_state.alle_daten.get("akku", {})
    ppv = akku.get("ppv", 0)
    app_state.ppv_mittelwert = int(mittelwert_get(ppv, app_state.ppv_werte) + 0.5)
    dazu_sanft_soc = 0
    dazu =  0
    app_state.dazu_sanft_soc  = 0
    dazu_ppv = 0
    soc = app_state.soc
    max_soc = einst.get("max_soc", 99)
    min_soc = einst.get("min_soc", 30) # brauche nur hier also 30
    mittel_verbrauch = einst.get("mittel_verbrauch", 110)
    
    if einst.get('akku_sanft', False) and  soc > min_soc:
        einspeise_gesamt =  app_state.solax_l_mittelwert + app_state.ppv_mittelwert - mittel_verbrauch
        if einspeise_gesamt > 26: # 26 min für hms8002t
            dazu_sanft_soc = int((einspeise_gesamt - app_state.pro_stunde) /
                                      ((einst.get("sanft_soc_meher",15) + 100) / 100))   
            app_state.dazu_sanft_soc = dazu_sanft_soc
    # -------------------------------------------------
    # Akku entladen
    # -------------------------------------------------
    if einst.get("akku_entladen"):
            if soc >= max_soc:
                app_state.akku_entladen_zustand = True
            if app_state.akku_entladen_zustand :
                if soc >= max_soc - 5:
                    dazu = einst.get("max_limit", 800)
                else:
                    app_state.akku_entladen_zustand = False
    # -------------------------------------------------
    # PV-Überschuss
    # -------------------------------------------------    
    if einst.get("akku_ppv") or soc >= max_soc - 5 :
            if soc >=einst.get("ppv_soc_ab", 90):
                app_state.akku_ppv_zustand = True
            if app_state.akku_ppv_zustand :
                if soc >= einst.get("ppv_soc_ab", 90) - 2:               
                    ppv_beide = app_state.ppv_mittelwert
                    if einst.get("solax_l_mittelwert_nutzen"):
                        ppv_beide += app_state.solax_l_mittelwert
                    if ppv_beide > mittel_verbrauch:
                        dazu_ppv = ppv_beide - mittel_verbrauch
                else:
                    app_state.akku_ppv_zustand = False
    # -------------------------------------------------
    # Höchsten dazu-Wert verwenden
    # -------------------------------------------------
    dazu = max(dazu, dazu_ppv, dazu_sanft_soc)
    if app_state.bool_dazu_intervall and app_state.akku_sanft_zeit :
        dazu += int(einst.get("dazu_sanft", 0)) 
    await sende_dazu(app_state, dazu)

def get_nachtzeten(app_state: AppState):
    try:
        sunrise_str = app_state.sonnenaufgang
        sunset_str  = app_state.sonnenuntergang

        if sunrise_str and sunset_str:
            sunrise = datetime.strptime(sunrise_str, "%H:%M:%S")
            sunset = datetime.strptime(sunset_str, "%H:%M:%S")

            kor_aufgang = app_state.einstellungen.get("kor_aufgang", 0)
            kor_unter = app_state.einstellungen.get("kor_unter", 0)

            startnacht = sunset - timedelta(minutes=kor_unter)
            endnacht = sunrise + timedelta(minutes=kor_aufgang)

            app_state.startnacht = startnacht.strftime("%H:%M")
            app_state.endnacht   = endnacht.strftime("%H:%M")

    except Exception:
        logger.exception("Nachtfenster konnte nicht berechnet werden")

async def reset_heute_werte(app_state: AppState):
    letzter_reset = app_state.einstellungen.get("tag_0", 0)
    aktueller_tag = date.today().timetuple().tm_yday
    if letzter_reset == aktueller_tag:
        return
    heute = date.today()
    aktueller_monat = heute.month
    aktuelles_jahr = heute.year
    # ==========================================
    # Aktuelle Zählerstände
    # ==========================================
    strom_daten = app_state.alle_daten.get("strom", {})
    hms_daten   = app_state.alle_daten.get("hms",   {})
    akku_daten  = app_state.alle_daten.get("akku",  {})
    solax_daten = app_state.alle_daten.get("solax", {})

    einspeise = strom_daten.get("Einspeise", 0)
    gesamt    = strom_daten.get("Gesamt", 0)
    hms       = hms_daten.get("gesamt", 0)
    akku      = akku_daten.get("eacTotal", 0)
    solax     = solax_daten.get("gesamt", 0)
    # Gestern speichern
    werte_alt = get_heute_werte(app_state.alle_daten,app_state.einstellungen) or {}
    werte_alt["datum"] = (date.today() - timedelta(days=1)).strftime("%d.%m.%y")
    werte_alt["tag_t"] = letzter_reset
    # Neue Tagesstartwerte
    datum_alt = heute - timedelta(days=1)
    werte_neu = {
        "datum": datum_alt.strftime("%d.%m.%y"),
        "tag_0": letzter_reset,
        "einspeise_0": einspeise,
        "gesamt_0": gesamt,
        "hms_0":hms,
        "growatt_0": akku,
        "solax_0": solax
    }
    await speichere_tageswerte(werte_neu,dateiname="tageswerte0.csv", feldreihenfolge=FELDREIHENFOLGE)
    # Neuer Monat
    if app_state.einstellungen.get("monat_0") != aktueller_monat:
        logger.info("📅 Neuer Monat – Monatsstartwerte setzen")
        monat_start = {
            "monat_0": aktueller_monat,
            "einspeise_monat_0": einspeise ,
            "gesamt_monat_0":gesamt ,
            "hms_monat_0":hms,
            "growatt_monat_0":akku,
            "solax_monat_0":solax
        }
        app_state.einstellungen.update(monat_start)
    if app_state.einstellungen.get("jahr_0") != aktuelles_jahr:
        logger.info("🎉 Neues Jahr – Jahresstartwerte setzen")
        jahr_start = {
            "jahr_0": aktuelles_jahr,
            "einspeise_jahr_0": einspeise,
            "gesamt_jahr_0":gesamt,
            "hms_jahr_0":hms,
            "growatt_jahr_0":akku,
            "solax_jahr_0":solax
        }
        app_state.einstellungen.update(jahr_start)
    # Einstellungen aktualisieren
    app_state.einstellungen.update(werte_neu)
    app_state.einstellungen["heute"] = date.today().strftime("%d.%m.%Y")
    app_state.einstellungen["tag_0"] = aktueller_tag
    astro_werte(app_state)
    get_nachtzeten(app_state)
    await speichere_einstellungen(app_state, app_state.einstellungen)
    logger.info("[neu start] Tagesstartwerte zurückgesetzt:")
    rotate_logs()
    