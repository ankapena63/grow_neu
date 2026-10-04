from datetime import datetime
import logging
import time
import asyncio

from units.state import AppState
from units.dose_routes import  dose_tuya
from units.funkzii import (
   sende_push,
   abfrage_hms,
   speichere_aktuell_wert,
   abfrage_tasmota,
   abfrage_strom,
   abfrage_solax_local,
   abfrage_solax,
   speichere_aktuell_csv,
   haus_verbrauch_get,
   zeitstempel,
   setze_hms_limit
)
from units.unit_hms import (
    lese_hms_powerlimiter,
    setze_hms_powerlimiter,
    lese_hms_powerlimiter_status,
    schalte_hms_wr,
)
from units.logic import rechne_dazu, reset_heute_werte

logger = logging.getLogger(__name__)

def stunden_bis_nacht_get(app_state: AppState):
    jetzt = datetime.now()
    now = jetzt.strftime("%H:%M")
    nacht = (app_state.startnacht <= now or now <= app_state.endnacht)
    app_state.nachtzeit= nacht
    max_s = app_state.einstellungen.get('max_soc',99)
    soc = app_state.soc
    app_state.brauche_watt =  round(( max_s -soc) * app_state.einstellungen.get('watt_max',4000) / 100 , 2)
    app_state.pro_stunde    = app_state.brauche_watt
    if nacht :
      return 0
    heute = jetzt.strftime("%Y-%m-%d")
    start_zeit = datetime.strptime(f"{heute} {app_state.startnacht}", "%Y-%m-%d %H:%M")
    diff = start_zeit - jetzt
    stunden_bis_nacht = round(diff.total_seconds() / 3600, 2)
    if stunden_bis_nacht > 1 :
      app_state.pro_stunde    = round(app_state.brauche_watt  / stunden_bis_nacht, 2)
    return stunden_bis_nacht

def get_web_daten(app_state: AppState):
   web = {
       "dazu"              : app_state.dazu,
       "haus_verbrauch"    : haus_verbrauch_get(app_state),
       "stunden_bis_nacht" : app_state.stunden_bis_nacht,
       "brauche_watt"      : app_state.brauche_watt,
       "pro_stunde"        : app_state.pro_stunde,
       "akku_sanft_zeit"   : app_state.akku_sanft_zeit,
       "dazu_intervall"    : app_state.dazu_intervall,
       "dazu_sanft_soc"    : app_state.dazu_sanft_soc,
       "sonnenaufgang"     : app_state.sonnenaufgang,
       "sonnenuntergang"   : app_state.sonnenuntergang,
       "tageslange"        : app_state.tageslange,
       "startnacht"        : app_state.startnacht,
       "endnacht"          : app_state.endnacht,
       "nachtzeit"         : app_state.nachtzeit,
       "dose_mode"         : app_state.dose_mode,
       "dose_relay_state"  : app_state.dose_relay_state,
       "dose_watt"         : app_state.dose_watt,
       "solax_l_mittelwert": app_state.solax_l_mittelwert,
       "ppv_mittelwert"    : app_state.ppv_mittelwert,
       "temperature"       : app_state.temperature
    }
   return web
 
async def pruefe_dose(app_state: AppState, zeit,takt = 300):
   if (zeit- app_state.last_dose_check) > takt:
           try:
                await dose_tuya(app_state)
           except Exception: # Variable umbenannt
                logger.exception("[Dose] Fehler ")
           finally:
                app_state.last_dose_check = zeit
   return

async def pruefe_kochen(app_state: AppState, zeit):
    soc = app_state.soc
    verbleibend = app_state.kochen_end - zeit
    if (soc < app_state.einstellungen.get("kochen_soc_min", 30)
        or verbleibend <= 0):
        app_state.kochen = False
        app_state.kochen_zeit = 0.0
        await rechne_dazu(app_state)
        logging.info("KOCHEN AUS: SOC zu niedrig oder _Zeit Abgelaufen")
        return
    if (app_state.nachtzeit and app_state.einstellungen.get("nacht_nur_0_schalter", False)):
        logging.info("KOCHEN AUS:Nachts nur 0   ein")
        app_state.kochen = False
        app_state.kochen_zeit = 0.0
        await rechne_dazu(app_state)
    app_state.kochen_zeit = round(verbleibend / 60, 2)
    return

def pruefe_dazu_intervall(app_state: AppState, zeit):
    verbleibend = round( app_state.dazu_intervall_dauer * 60 - (zeit - app_state.dazu_intervall_start), 2)
    if verbleibend <= 0:
        app_state.dazu_intervall = 0.0
        app_state.bool_dazu_intervall  = False
        app_state.akku_sanft_zeit = False
    else:
        app_state.dazu_intervall = round(verbleibend / 60, 2)
    return

async def pruefe_hms(app_state: AppState, zeit,takt :int = 30):
    if (zeit - app_state.start_hms > takt) or app_state.erste_abfrage:
        logger.info("📡 HMS✅ %s Sek",takt)
        app_state.alle_daten["hms"] = await abfrage_hms(app_state, app_state.alle_daten.get("hms", {}),takt)
        app_state.start_hms = zeit
        if app_state.einstellungen.get("aktuell_aktiv", True):
            speichere_aktuell_wert(app_state, "hms", app_state.alle_daten["hms"].get("aktuell", 0))
    return

async def pruefe_strom(app_state: AppState, zeit,takt :int = 30):
    if (zeit - app_state.start_strom > takt) or app_state.erste_abfrage:
        logger.debug("zum Strom %s Sek",takt)
        
        #daten = await lese_hms_powerlimiter()
        #await setze_hms_powerlimiter(True)
        #await schalte_hms_wr(True)
        # await lese_hms_powerlimiter_status()

        try:
            if app_state.einstellungen.get("abfrage_tasmota", False):
                result = { "strom": await abfrage_tasmota(app_state, app_state.alle_daten.get("strom") or {}, takt) }
            else:
                result = { "strom": await abfrage_strom(app_state, app_state.alle_daten.get("strom") or {},app_state.zugang.get("ip_smart", "123"), takt) }
            app_state.alle_daten.update(result)
            if app_state.einstellungen.get("aktuell_aktiv", True):
                  speichere_aktuell_wert(app_state, "strom", result["strom"].get("Actuel", 0))
        except Exception:
                logger.exception("[Fehler] ❌ Stromabfrage fehlgeschlagen")
        finally:
                app_state.start_strom = zeit
    return

async def pruefe_solax_local(app_state: AppState, zeit,takt :int = 15):
    if (zeit - app_state.start_solax_l > takt) or app_state.erste_abfrage:
        if app_state.alle_daten.get("solax", {}).get("acpower", 0) != 0:
           app_state.solax_local = await abfrage_solax_local(app_state, takt)
           app_state.start_solax_l = zeit
    if (zeit - app_state.start_solax_l > takt*10):
        app_state.solax_local["fehler"] = "Lokale Solax-API zu lang nicht erreichbar"
        app_state.solax_local["zeit_fehler"] = zeitstempel()
    return

async def pruefe_solax_cloud(app_state: AppState, zeit,takt :int = 60):
    if (zeit - app_state.start_solax_c ) > takt or app_state.erste_abfrage:
        logger.info("☁️ Solax C✅ %s Sek",takt)
        app_state.alle_daten["solax"] = await abfrage_solax(app_state, app_state.alle_daten.get("solax", {}),takt)
        app_state.start_solax_c = zeit
    return

async def akku_daten(app_state: AppState, alt_daten: dict, takt :int = 60) -> dict:
    try:
        if app_state.einstellungen.get("abfrage_growatt", False):
            status2, status1 = await asyncio.gather(
               app_state.growatt.get_status(takt),               
               app_state.growatt.run_with_lock(app_state.growatt.get_noah_queryLastData, 
               takt,
               cooldown=60)
            )
            # Fallback für status1
            if not status1:
                status1 = alt_daten or {}           
            # Merge mit status2, falls vorhanden
            if status2:
                status = {**status1, **status2}  # status2 überschreibt status1
            else:
                status = status1  # nur status1 vorhanden
        else:
            status = await app_state.growatt.get_iobroker() or {}
            status["zeit_meine"] = zeitstempel()
        temp1 = status.get("battery1Temp", 0)
        temp2 = status.get("battery2Temp", 0) # Falls eine zweite vorhanden ist
        if temp1 > 44 or temp2 > 44:
                   # Den höchsten Wert für die Nachricht ermitteln
            max_temp = max(temp1, temp2)
            msg = f"⚠️ Akku zu heiß: {max_temp}°C! Bitte für Kühlung/Schatten sorgen."
            # Nutzt deine neue sende_push Funktion (Pause 600s = 10 Min)
            await sende_push(app_state, msg,600,5)
        status_akku = status.get("status", 1)
        if status_akku != 1:
            await sende_push(app_state, f"Akku status: {status_akku}",3600,4) # jede stunde
        return status
    except Exception as e:
        logger.exception("[Growatt] Fehler")
        alt_daten = alt_daten or {}
        alt_daten["fehler"] = str(e)
        alt_daten["zeit_fehler"] = zeitstempel()
        return alt_daten

async def pruefe_akku(app_state: AppState, zeit,takt = 60):
    solax_l_mittelwert_nutzen = app_state.einstellungen.get("solax_l_mittelwert_nutzen", False)
    if (zeit - app_state.start_akku > takt) or app_state.erste_abfrage:
        logger.info("🔋Akkus %s Sek",takt)
        app_state.alle_daten["akku"] = await akku_daten(app_state, app_state.alle_daten.get("akku", {}), takt)
        if solax_l_mittelwert_nutzen and not app_state.nachtzeit:
            app_state.solax_local = await abfrage_solax_local(app_state, takt)
            app_state.start_solax_l = zeit
        app_state.start_akku = zeit
        await rechne_dazu(app_state)
    return

async def pruefe_48st(app_state: AppState, zeit,takt =3600):
    if not app_state.einstellungen.get("aktuell_aktiv", True) :
        return
    if( zeit  == 0 or zeit - app_state.aktuell_letztes_speichern >= takt):
         try:
            logger.info("💾 [Backup] Speichere stündliches Aktuell-Daten-Backup...")
            await speichere_aktuell_csv(app_state)
         except Exception :
            logger.error("❌ Fehler beim Backup-CSV-Speichern")
         finally:
            if zeit != 0:
                app_state.aktuell_letztes_speichern = zeit
    return

async def pruefe_hms_limit(app_state: AppState, zeit,nullen):  
        if app_state.start_hms0 <2:
          app_state.start_hms0 += 1
          logger.info("⏳ HMS-Limit: %s Takt Startverzögerung",app_state.start_hms0)
          return
        if nullen:
            hms_limit_soll = int(app_state.einstellungen.get("hms_limit_soll", 100))
            hms_limit_aktuell = ( app_state.alle_daten
                               .get("hms", {})
                               .get("limit", 0))
            if abs(hms_limit_aktuell - hms_limit_soll) > 10:
                if await setze_hms_limit(app_state, hms_limit_soll):
                   logger.info("HMS neues Limit: %s W (vorher %s W)",hms_limit_soll,hms_limit_aktuell)

def berechne_takte(app_state: AppState, benutzer_activ: bool) -> dict:
    einst = app_state.einstellungen
    aktuell_aktiv = einst.get("aktuell_aktiv", False)
    if benutzer_activ:
        return {
            "akku": einst.get("takt_akku", 61),
            "hms": einst.get("takt_hms", 25),
            "solax_c": einst.get("takt_solax_c", 150),
            "solax_l": einst.get("takt_solax_l", 15),
            "strom": einst.get("takt_strom", 15),
        }
    takt = einst.get("takt_akku_inactiv", 120)
    takte = {
        "akku": takt,
        "hms": takt,
        "solax_c": 301,
        "solax_l": takt,
        "strom": takt,
    }
    nur_growatt = (
        app_state.nachtzeit
        and not app_state.erste_abfrage
        and not benutzer_activ
    )
    if nur_growatt:
        takte.update({
            "akku": 300,
            "strom": 599,
            "hms": 600,
            "solax_c": 600,
            "solax_l": 600,
        })
    takte["solax_c"] = max(600, takte["solax_c"])
    if aktuell_aktiv:
        takte["strom"] = 60
        takte["hms"] = 60

    if app_state.einstellungen.get("hms_bekommt_null", False):
        takte["strom"] = min(120, takte["strom"])
        takte["hms"] = takte["strom"]

    return takte

async def wiederholte_takt(app_state: AppState) -> None:
    await reset_heute_werte(app_state)
    zeit_jetzt = time.monotonic()

    nullen = app_state.einstellungen.get("hms_bekommt_null", False)

    app_state.stunden_bis_nacht = stunden_bis_nacht_get(app_state)
    benutzer_activ = (
        zeit_jetzt - app_state.last_activity
        < app_state.einstellungen.get("takt_benutzrer_activ", 50)
    )
    if benutzer_activ != app_state.benutzer_activ:
        app_state.benutzer_activ = benutzer_activ
        app_state.takt_geaendert = True
    if app_state.nachtzeit != app_state.nachtzeit_alt:
        app_state.nachtzeit_alt = app_state.nachtzeit
        app_state.takt_geaendert = True
    if app_state.takt_geaendert:
        app_state.takte = berechne_takte(app_state, benutzer_activ)
        app_state.takt_geaendert = False
    logger.debug(
        "Takte: Akku=%s HMS=%s SolaxC=%s SolaxL=%s Strom=%s",
        app_state.takte["akku"],
        app_state.takte["hms"],
        app_state.takte["solax_c"],
        app_state.takte["solax_l"],
        app_state.takte["strom"],
    )
    pruefe_dazu_intervall(app_state, zeit_jetzt)
    await pruefe_48st(app_state, zeit_jetzt, 3600 * 2)
    await pruefe_dose(
        app_state,
        zeit_jetzt,
        app_state.einstellungen.get("takt_dose", 300),
    )
    if app_state.kochen:
        await pruefe_kochen(app_state, zeit_jetzt)
    await pruefe_akku(app_state, zeit_jetzt, app_state.takte["akku"])

    await pruefe_hms_limit(app_state, zeit_jetzt, nullen)

    await pruefe_solax_cloud(app_state, zeit_jetzt, app_state.takte["solax_c"])
    await pruefe_solax_local(app_state, zeit_jetzt, app_state.takte["solax_l"])
    await pruefe_hms(app_state, zeit_jetzt, app_state.takte["hms"])
    await pruefe_strom(app_state, zeit_jetzt, app_state.takte["strom"])
    app_state.erste_abfrage = False
