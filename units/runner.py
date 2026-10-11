"""Central scheduler for device polling and application control."""
from datetime import datetime
import logging
import time
from units.history import speichere_aktuell_csv
from units.calculations import reset_heute_werte
from units.calculations import mittelwert_get
from units.configuration import mache_session
from units.state import AppState

logger = logging.getLogger(__name__)

async def sende_dazu(app_state: AppState, wert):
    soc = app_state.soc
    if not (
        app_state.nachtzeit
        and app_state.einstellungen.get("nacht_nur_0_schalter", False)
    ):
        if (
            app_state.kochen
            and app_state.kochen_zeit > 0
            and soc > app_state.einstellungen.get("kochen_soc_min", 30)
        ):
            wert += int(app_state.einstellungen.get("kochen_wert", 600))
    dazu_alt = app_state.dazu
    zeit_jetzt = time.monotonic()

    diff = abs(dazu_alt - wert)
    timeout = (
        zeit_jetzt - app_state.start_dazu_senden
    ) > app_state.einstellungen.get("dazu_senden", 60)

    muss_senden = (
        diff > app_state.einstellungen.get("dazu_tolleranz", 0)
        or (timeout and wert != 0)
        or (wert == 0 and dazu_alt != 0)
    )
    if muss_senden:
        if app_state.einstellungen["abfrage_tasmota"]:
            antwort = await app_state.strom.sende_tasmota(wert)
            logger.debug("[SEND]  tasmota %s", antwort)
        else:
            antwort = await app_state.strom.sende_smart(wert)
            logger.debug("[SEND]  smart %s", antwort)

        if "error" not in antwort:
            app_state.dazu = wert
            app_state.start_dazu_senden = zeit_jetzt
            logger.info("[SEND dazu] ✅: %s ", wert)
            logger.debug(
                "[SEND dazu] ✅: %s (Diff: %s, Timeout: %s)",
                wert,
                diff,
                timeout,
            )
        else:
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
    app_state.ppv_mittelwert = int(
        mittelwert_get(ppv, app_state.ppv_werte) + 0.5
    )
    dazu_sanft_soc = 0
    dazu = 0
    app_state.dazu_sanft_soc = 0
    dazu_ppv = 0
    soc = app_state.soc
    max_soc = einst.get("max_soc", 99)
    min_soc = einst.get("min_soc", 30)
    mittel_verbrauch = einst.get("mittel_verbrauch", 110)

    if einst.get("akku_sanft", False) and soc > min_soc:
        einspeise_gesamt = (
            app_state.solax_l_mittelwert
            + app_state.ppv_mittelwert
            - mittel_verbrauch
        )
        if einspeise_gesamt > 26:
            dazu_sanft_soc = int(
                (einspeise_gesamt - app_state.pro_stunde)
                / ((einst.get("sanft_soc_meher", 15) + 100) / 100)
            )
            app_state.dazu_sanft_soc = dazu_sanft_soc

    if einst.get("akku_entladen"):
        if soc >= max_soc:
            app_state.akku_entladen_zustand = True
        if app_state.akku_entladen_zustand:
            if soc >= max_soc - 5:
                dazu = einst.get("max_limit", 800)
            else:
                app_state.akku_entladen_zustand = False

    if einst.get("akku_ppv") or soc >= max_soc - 5:
        if soc >= einst.get("ppv_soc_ab", 90):
            app_state.akku_ppv_zustand = True
        if app_state.akku_ppv_zustand:
            if soc >= einst.get("ppv_soc_ab", 90) - 2:
                ppv_beide = app_state.ppv_mittelwert
                if einst.get("solax_l_mittelwert_nutzen"):
                    ppv_beide += app_state.solax_l_mittelwert
                if ppv_beide > mittel_verbrauch:
                    dazu_ppv = ppv_beide - mittel_verbrauch
            else:
                app_state.akku_ppv_zustand = False

    dazu = max(dazu, dazu_ppv, dazu_sanft_soc)
    if app_state.bool_dazu_intervall and app_state.akku_sanft_zeit:
        dazu += int(einst.get("dazu_sanft", 0))
    await sende_dazu(app_state, dazu)

async def sende_ntfy(session, nachricht: str, prio: int) -> bool:
    headers = {
        "Priority": str(prio),
        "Title": "Solar-Monitor",
        "Tags": "warning" if prio >= 4 else "info",
    }
    url = "https://ntfy.sh/SolaxHmsGrowattvvv"
    async with session.post(
        url,
        data=nachricht.encode("utf-8"),
        headers=headers,
    ) as response:
        if response.status == 200:
            logger.info("✅ Push Prio: %s gesendet", prio)
            return True
        error_text = await response.text()
        logger.error(
            "❌ ntfy Fehler %s : %s",
            response.status,
            error_text,
        )
        return False

async def sende_push(app_state, nachricht, pause: int = 3600, prio: int = 3):
    if not app_state.einstellungen.get("nachricht_app", False):
        return
    jetzt = time.time()
    if not hasattr(app_state, "letzte_push_zeiten"):
        app_state.letzte_push_zeiten = {}
    letzte_zeit = app_state.letzte_push_zeiten.get(prio, 0)
    if jetzt - letzte_zeit < pause:
        return

    session = await mache_session(app_state, "session_push")
    try:
        if await sende_ntfy(session, nachricht, prio):
            app_state.letzte_push_zeiten[prio] = jetzt
    except Exception:
        logger.exception("❌ Push-Verbindung fehlgeschlagen")

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
        return
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

class AppRunner:
    """Steuert den regelmäßigen Ablauf der Geräteabfragen."""

    def __init__(self, app_state: AppState):
        self.app_state = app_state

    async def wiederholte_takt(self) -> None:
        app_state = self.app_state

        await reset_heute_werte(app_state)

        jetzt = datetime.now()
        now = jetzt.strftime("%H:%M")
        zeit_jetzt = time.monotonic()

        app_state.nachtzeit = (
            app_state.startnacht <= now
            or now <= app_state.endnacht
        )

        app_state.stunden_bis_nacht = (
            stunden_bis_nacht_get(app_state)
        )

        app_state.benutzer_activ = (
            zeit_jetzt - app_state.last_activity
            < app_state.einstellungen.get(
                "takt_benutzrer_activ", 10
            )
        )

        pruefe_dazu_intervall(app_state, zeit_jetzt)
        await pruefe_48st(app_state, zeit_jetzt)

        # Dose bleibt unverändert.
        if app_state._dose_manager is None:
            logger.warning(
                "[Dose] Manager ist nicht initialisiert"
            )
        else:
            await app_state._dose_manager.pruefe(zeit_jetzt)

        # Kochen bleibt unverändert.
        if app_state.kochen:
            await pruefe_kochen(app_state, zeit_jetzt)

        # Geräteabfragen in der bisherigen Reihenfolge.
        await app_state.growatt.pruefe(zeit_jetzt)
        await app_state.solax.pruefe(zeit_jetzt)
        await app_state.hms.pruefe(zeit_jetzt)
        await app_state.strom.pruefe(zeit_jetzt)

        app_state.erste_abfrage = False


async def wiederholte_takt(app_state: AppState) -> None:
    """Übergang für bestehende Aufrufer."""
    runner = AppRunner(app_state)
    await runner.wiederholte_takt()
