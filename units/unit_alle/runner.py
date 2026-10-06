"""Central scheduler for device polling and application control."""

from datetime import datetime
import logging
import time

from units.unit_dose import dose_tuya
from units.unit_alle.history import speichere_aktuell_csv
from units.unit_alle.calculations import reset_heute_werte
from units.unit_alle.power import rechne_dazu
from units.state import AppState
#from units.unit_battery import pruefe_akku

logger = logging.getLogger(__name__)


def stunden_bis_nacht_get(app_state: AppState) -> float:
    jetzt = datetime.now()
    now = jetzt.strftime("%H:%M")
    nacht = app_state.startnacht <= now or now <= app_state.endnacht
    app_state.nachtzeit = nacht
    max_s = app_state.einstellungen.get("max_soc", 99)
    soc = app_state.soc
    app_state.brauche_watt = round(
        (max_s - soc) * app_state.einstellungen.get("watt_max", 4000) / 100,
        2,
    )
    app_state.pro_stunde = app_state.brauche_watt
    if nacht:
        return 0
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


async def pruefe_dose(
    app_state: AppState,
    zeit: float,
    takt: int = 300,
) -> None:
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
        logger.info("KOCHEN AUS: SOC zu niedrig oder _Zeit Abgelaufen")
        return
    if (
        app_state.nachtzeit
        and app_state.einstellungen.get("nacht_nur_0_schalter", False)
    ):
        logger.info("KOCHEN AUS:Nachts nur 0   ein")
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


async def pruefe_48st(
    app_state: AppState,
    zeit: float,
    takt: int = 3600,
) -> None:
    if not app_state.einstellungen.get("aktuell_aktiv", True):
        return
    if zeit == 0 or zeit - app_state.aktuell_letztes_speichern >= takt:
        try:
            logger.info("💾 [Backup] Speichere stündliches Aktuell-Daten-Backup...")
            await speichere_aktuell_csv(app_state)
        except Exception:
            logger.error("❌ Fehler beim Backup-CSV-Speichern")
        finally:
            if zeit != 0:
                app_state.aktuell_letztes_speichern = zeit


def berechne_takte(
    app_state: AppState,
    benutzer_activ: bool,
) -> dict[str, int]:
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
    app_state.benutzer_activ = benutzer_activ
    
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
    await app_state.growatt.pruefe_akku( 
                                        zeit_jetzt, 
                                        app_state.takte["akku"])
    await app_state.hms.pruefe_limit(zeit_jetzt, nullen)
    await app_state.solax.pruefe_cloud(
        zeit_jetzt,
        app_state.takte["solax_c"],
    )
    await app_state.solax.pruefe_local(
        zeit_jetzt,
        app_state.takte["solax_l"],
    )
    await app_state.hms.pruefe( zeit_jetzt)
    await app_state.strom.pruefe(
        zeit_jetzt,
        app_state.takte["strom"],
    )
    app_state.erste_abfrage = False
