"""Dashboard routes."""
from . import routes, _app_state
from quart import redirect, render_template, request
from units.calculations import (
    get_heute_werte,
    get_jahres_werte,
    get_monats_werte,
)
from units.configuration import (
    load_tageswerte,
    run_sshd,
    speichere_einstellungen,
    start_sshd,
    stop_sshd,
)
from units.calculations import haus_verbrauch_get
from units.runner import rechne_dazu
from units.state import AppState
import logging
import time


class DashboardManager:
    """Verwaltet Dashboard- und Anzeigefunktionen."""

    def get_web_daten(self, app_state: AppState) -> dict:
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

    async def tageswerte(self):
        state: AppState = _app_state()
        return await render_template(
            "tageswerte.html",
            web=self.get_web_daten(state),
            einstellungen=state.einstellungen,
            datei_daten0=load_tageswerte("tageswerte0.csv"),
            headers=["Tag", "E🏠", "V🏠", "HMS", "🔋", "Sol"],
        )

    async def dashboard(self):
        state: AppState = _app_state()
        state.einstellungen["server_sshd"] = run_sshd(state)
        return await render_template(
            "dashboard.html",
            daten=state.alle_daten,
            tag_daten=get_heute_werte(
                state.alle_daten, state.einstellungen
            ),
            monat_daten=get_monats_werte(
                state.alle_daten, state.einstellungen
            ),
            jahr_daten=get_jahres_werte(
                state.alle_daten, state.einstellungen
            ),
            einstellungen=state.einstellungen,
            version=state.version,
            web=self.get_web_daten(state),
            solax_local=state.solax_local,
        )

    async def server_sshd(self):
        state = _app_state()
        if run_sshd(state):
            stop_sshd(state)
        else:
            start_sshd(state)
        return redirect("/")

    async def kochen_start(self):
        state: AppState = _app_state()
        data = await request.get_json()
        try:
            interval = int(data.get("kochen_zeit", 0))  # Minuten
            kochen_soc_min = int(data.get("kochen_soc_min", 30))
            kochen_wert = int(data.get("kochen_wert", 1400))
        except (TypeError, ValueError):
            return {"ok": False, "fehler": "Ungültige Koch-Einstellungen"}

        # Grenzen
        kochen_soc_min = max(30, min(90, kochen_soc_min))
        kochen_wert = max(100, min(3000, kochen_wert))
        akku_soc = state.soc

        if interval <= 0:
            state.kochen = False
            return {"ok": False, "fehler": "Zeit soll nich 0 sein"}

        if akku_soc <= kochen_soc_min:
            state.kochen = False
            state.kochen_zeit = 0.0
            state.kochen_end = 0.0
            return {
                "ok": False,
                "fehler": (
                    f"Akku SOC zu klein: {akku_soc:.0f}% "
                    f"(mindestens {kochen_soc_min}%)"
                ),
            }

        # Einstellungen nur speichern, wenn sie sich geändert haben.
        alt_soc_min = state.einstellungen.get("kochen_soc_min", 30)
        alt_wert = state.einstellungen.get("kochen_wert", 1400)
        state.einstellungen["kochen_soc_min"] = kochen_soc_min
        state.einstellungen["kochen_wert"] = kochen_wert
        if alt_soc_min != kochen_soc_min or alt_wert != kochen_wert:
            await speichere_einstellungen(state, state.einstellungen)

        state.kochen = True
        logging.info("KOCHEN An: für: %s min %s Watt", interval, kochen_wert)
        state.kochen_zeit = interval
        state.kochen_end = time.monotonic() + interval * 60
        await rechne_dazu(state)
        return {
            "ok": True,
            "kochen": True,
            "kochen_zeit": state.kochen_zeit,
            "kochen_end": state.kochen_end,
            "kochen_soc_min": state.einstellungen["kochen_soc_min"],
            "kochen_wert": state.einstellungen["kochen_wert"],
        }

    async def kochen_stop(self):
        state: AppState = _app_state()
        state.kochen = False
        state.kochen_zeit = 0.0
        state.kochen_end = 0.0
        await rechne_dazu(state)
        logging.info("KOCHEN Ausgeschaltet")
        return {"ok": True, "kochen": False}

    async def diagramm(self):
        return await render_template("diagramm.html")

    async def aktuell(self):
        return await render_template("aktuell.html")

    async def stat(self):
        return await render_template("stat.html")

    async def log_seite(self):
        return await render_template("log.html")


dashboard_manager = DashboardManager()


def get_web_daten(app_state: AppState) -> dict:
    """Kompatibilitätswrapper für bestehende Importe."""
    return dashboard_manager.get_web_daten(app_state)


@routes.route("/tageswerte")
async def tageswerte():
    return await dashboard_manager.tageswerte()


@routes.route("/")
async def dashboard():
    return await dashboard_manager.dashboard()


@routes.route("/server_sshd", methods=["POST"])
async def server_sshd():
    return await dashboard_manager.server_sshd()


@routes.route("/kochen_start", methods=["POST"])
async def kochen_start():
    return await dashboard_manager.kochen_start()


@routes.route("/kochen_stop", methods=["POST"])
async def kochen_stop():
    return await dashboard_manager.kochen_stop()


@routes.route("/dia")
async def diagramm():
    return await dashboard_manager.diagramm()


@routes.route("/aktuell")
async def aktuell():
    return await dashboard_manager.aktuell()


@routes.route("/stat")
async def stat():
    return await dashboard_manager.stat()


@routes.get("/log")
async def log_seite():
    return await dashboard_manager.log_seite()
