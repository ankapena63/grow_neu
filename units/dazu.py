"""Steuerung der Einspeisung und Akku-Leistung."""
import logging
import time

from units.calculations import mittelwert_get
from units.state import AppState

logger = logging.getLogger(__name__)


class DazuManager:
    """Berechnet die Zusatzleistung und sendet sie an das Smart-Gerät."""

    def __init__(self, app_state: AppState):
        self.app_state = app_state

    async def sende_dazu(self, wert):
        app_state = self.app_state
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

    async def rechne_dazu(self):
        app_state = self.app_state
        einst = app_state.einstellungen

        if app_state.nachtzeit or einst.get("nur_nulleinspeisung"):
            await self.sende_dazu(0)
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

        await self.sende_dazu(dazu)
