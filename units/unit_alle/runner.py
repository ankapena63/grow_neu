"""Central scheduler for device polling and application control."""
from datetime import datetime
import logging
import time
from units.unit_dose import dose_tuya
from units.unit_alle.history import speichere_aktuell_csv
from units.unit_alle.calculations import reset_heute_werte
from units.unit_alle.power import rechne_dazu
from units.state import AppState

logger = logging.getLogger(__name__)

def stunden_bis_nacht_get(app_state: AppState) -> float:
    jetzt = datetime.now()
    max_s = app_state.einstellungen.get("max_soc", 99)
    soc = app_state.soc
    app_state.brauche_watt = round(
        (max_s - soc) * app_state.einstellungen.get("watt_max", 4000) / 100,
        2,
    )
    app_state.pro_stunde = app_state.brauche_watt
    # 💡 Nutzt jetzt die im State berechnete Nachtzeit aus deiner Hauptschleife
    if app_state.nachtzeit:
        return 0.0
    heute = jetzt.strftime("%Y-%m-%d")
    start_zeit = datetime.strptime(
        f"{heute} {app_state.startnacht}",
        "%Y-%m-%d %H:%M",
    )
    diff = start_zeit - jetzt
    stunden_bis_nacht = round(diff.total_seconds() / 3600, 2)
    if stunden_bis_nacht > 1:
        app_state.pro_stunde = round(
            app_state.brauche_watt / stunden_bis_nacht,
            2,
        )
    return stunden_bis_nacht

async def pruefe_dose(app_state: AppState, zeit: float) -> None:
    takt = app_state.einstellungen.get("takt_dose", 300)
    if zeit - app_state.last_dose_check > takt:
        try:
            await dose_tuya(app_state)
        except Exception:
            logger.exception("[Dose] Fehler")
        finally:
            app_state.last_dose_check = zeit

async def pruefe_kochen(app_state: AppState, zeit: float) -> None:
    soc = app_state.soc
    verbleibend = app_state.kochen_end - zeit
    if (
        soc < app_state.einstellungen.get("kochen_soc_min", 30)
        or verbleibend <= 0
    ):
        app_state.kochen = False
        app_state.kochen_zeit = 0.0
        await rechne_dazu(app_state)
        logger.info("KOCHEN AUS: SOC zu niedrig oder _Zeit abgelaufen")
        return
    if (
        app_state.nachtzeit
        and app_state.einstellungen.get("nacht_nur_0_schalter", False)
    ):
        logger.info("KOCHEN AUS:Nachts nur 0 Einp.")
        app_state.kochen = False
        app_state.kochen_zeit = 0.0
        await rechne_dazu(app_state)
    app_state.kochen_zeit = round(verbleibend / 60, 2)

def pruefe_dazu_intervall(app_state: AppState, zeit: float) -> None:
    verbleibend = round(
        app_state.dazu_intervall_dauer * 60
        - (zeit - app_state.dazu_intervall_start),
        2,
    )
    if verbleibend <= 0:
        app_state.dazu_intervall = 0.0
        app_state.bool_dazu_intervall = False
        app_state.akku_sanft_zeit = False
    else:
        app_state.dazu_intervall = round(verbleibend / 60, 2)

async def pruefe_48st(app_state: AppState,zeit: float) -> None:
    if not app_state.einstellungen.get("aktuell_aktiv", True):
        return
    takt =  app_state.takt_48_datei
    if zeit == 0 or zeit - app_state.aktuell_letztes_speichern >= takt:
        try:
            logger.info("💾 [Backup]  Speichere 2 stündliches Aktuell-Daten-Backup...")
            await speichere_aktuell_csv(app_state)
        except Exception:
            logger.error("❌ Fehler beim Backup-CSV-Speichern")
        finally:
            if zeit != 0:
                app_state.aktuell_letztes_speichern = zeit

async def wiederholte_takt(app_state: AppState) -> None:
    await reset_heute_werte(app_state)
    jetzt = datetime.now()
    now = jetzt.strftime("%H:%M")
    zeit_jetzt = time.monotonic()
    #nullen = app_state.einstellungen.get("hms_bekommt_null", False)

    app_state.nachtzeit = app_state.startnacht <= now or now <= app_state.endnacht
    app_state.stunden_bis_nacht = stunden_bis_nacht_get(app_state)
    app_state.benutzer_activ = (
        zeit_jetzt - app_state.last_activity
        < app_state.einstellungen.get("takt_benutzrer_activ", 10)
    )    
    pruefe_dazu_intervall(app_state, zeit_jetzt)
    await pruefe_48st(app_state, zeit_jetzt)
    await pruefe_dose(app_state, zeit_jetzt)
    if app_state.kochen:
        await pruefe_kochen(app_state, zeit_jetzt)
    await app_state.growatt.pruefe(zeit_jetzt)
    await app_state.hms.pruefe_limit(zeit_jetzt)
    await app_state.solax.pruefe(zeit_jetzt)  #beide 
    await app_state.hms.pruefe(zeit_jetzt)
    await app_state.strom.pruefe(zeit_jetzt)
    
    app_state.erste_abfrage = False


