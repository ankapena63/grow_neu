"""API-Routen und Datenbereitstellung."""
from . import routes, _app_state
from datetime import date, datetime
from quart import jsonify, request
from units.calculations import EnergiewerteManager, StatusManager
from units.configuration import EinstellungenManager
from units.history import TageshistorieManager
from units.web.web_data import web_data_manager
from units.logg import LogManager, log_buffer
from units.state import AppState
import logging
import time

logger = logging.getLogger(__name__)


class ApiManager:
    """Verwaltet die API-Abfragen und stellt Anwendungsdaten bereit."""

    async def daten(self):
        state: AppState = _app_state()
        state.last_activity = time.monotonic()

        kochen_web = {
            "kochen": state.kochen,
            "kochen_zeit": state.kochen_zeit,
            "kochen_end": state.kochen_end,
            "kochen_soc_min": state.einstellungen.get(
                "kochen_soc_min", 30
            ),
            "kochen_wert": state.einstellungen.get(
                "kochen_wert", 1400
            ),
        }

        return {
            "daten": state.alle_daten,
            "tag_daten": EnergiewerteManager.get_heute_werte(
                state.alle_daten, state.einstellungen
            ),
            "monat_daten": EnergiewerteManager.get_monats_werte(
                state.alle_daten, state.einstellungen
            ),
            "jahr_daten": EnergiewerteManager.get_jahres_werte(
                state.alle_daten, state.einstellungen
            ),
            "status": StatusManager.gereate_status(state.status_html),
            "solax_local": state.solax_local,
            "web": web_data_manager.get_web_daten(_app_state()),
            "akku_login": state.growatt.akku_login_daten,
            "kochen": kochen_web,
            "einstellungen": state.einstellungen,
        }

    async def strom(self):
        state: AppState = _app_state()
        daten_strom = state.alle_daten.get("strom") or {}

        if not daten_strom:
            return jsonify({
                "error": "Keine gültigen Stromdaten verfügbar"
            }), 500

        return jsonify(daten_strom)

    def akku_cloud(self):
        state: AppState = _app_state()
        return jsonify({
            "Seite": "Akku Cloud",
            "meine_daten": state.alle_daten.get("akku", {}),
            "akku_login": state.roh.get("akku_login", {}),
            "akku_status": state.roh.get("akku_status", {}),
            "akku_token": state.roh.get("akku_token", {}),
        })

    def hms(self):
        state: AppState = _app_state()
        return jsonify({
            "Seite": "HNS-800-2T",
            "meine_daten": state.alle_daten.get("hms", {}),
            "server_roh": state.roh.get("hms", {}),
        })

    async def solax_cloud(self):
        state: AppState = _app_state()
        return jsonify({
            "Seite": "Solax Cloud",
            "meine_daten": state.alle_daten.get("solax", {}),
            "server_roh": state.roh.get("solax_c", {}),
        })

    async def solax_local(self):
        state: AppState = _app_state()
        state.solax_local = await state.solax.abfrage_local(
            state.einstellungen.get("takt_solax_l", 15)
        )
        return jsonify({
            "Seite": "Solax Local",
            "meine_daten": state.solax_local,
            "server_roh": state.roh.get("solax_l", {}),
        })

    async def parameter(self):
        state: AppState = _app_state()
        return jsonify(state.einstellungen)

    async def parameter_zugang(self):
        state: AppState = _app_state()

        # Zugangsdaten niemals im Klartext über die JSON-Route ausgeben.
        zugang_anzeigen = {}
        for key, value in state.zugang.items():
            name = key.lower()
            ist_geheim = (
                "password" in name
                or "token" in name
                or "secret" in name
                or "local_key" in name
                or name.endswith("_pas")
            )
            zugang_anzeigen[key] = (
                "********" if ist_geheim and value else value
            )

        return jsonify({
            "Seite": "parameter_zugang",
            "web_daten": web_data_manager.get_web_daten(state),
            "zugang": zugang_anzeigen,
        })

    async def status(self):
        state: AppState = _app_state()
        if not state.alle_daten:
            return jsonify({"error": "Keine Daten vorhanden"}), 500

        return jsonify({
            "alle": state.alle_daten,
            "status_html": state.status_html,
            "Takte": state.takte,
        })

    async def tages(self):
        state: AppState = _app_state()
        return jsonify(
            EnergiewerteManager.get_heute_werte(state.alle_daten, state.einstellungen),
            EnergiewerteManager.get_monats_werte(state.alle_daten, state.einstellungen),
            EnergiewerteManager.get_jahres_werte(state.alle_daten, state.einstellungen),
        )

    def roh(self):
        state: AppState = _app_state()
        return jsonify(state.roh)

    async def diagramm(self):
        jahr = int(request.args.get("jahr", date.today().year))
        monat = int(request.args.get("monat", date.today().month))
        modus = request.args.get("modus", "monat")
        tageswerte = TageshistorieManager.lese_tageswerte0()

        # Jahresansicht
        if modus == "jahr":
            monatswerte = []

            for m in range(1, 13):
                werte = []
                for wert in tageswerte:
                    datum = datetime.strptime(
                        wert["datum"], "%d.%m.%y"
                    ).date()
                    if datum.year == jahr and datum.month == m:
                        werte.append(wert)

                einspeise = round(
                    sum(wert["einspeise"] for wert in werte), 2
                )
                gesamt = round(
                    sum(wert["gesamt"] for wert in werte), 2
                )
                hms = round(
                    sum(wert["hms"] for wert in werte), 2
                )
                growatt = round(
                    sum(wert["growatt"] for wert in werte), 2
                )
                solax = round(
                    sum(wert["solax"] for wert in werte), 2
                )

                # Solarverbrauch
                solarverbrauch = round(
                    hms + solax - einspeise, 2
                )
                monatswerte.append({
                    "monat": m,
                    "einspeise": einspeise,
                    "gesamt": gesamt,
                    "hms": hms,
                    "growatt": growatt,
                    "solax": solax,
                    "solarverbrauch": solarverbrauch,
                })

            monatsnamen = [
                "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                "Jul", "Aug", "Sep", "Okt", "Nov", "Dez",
            ]

            return jsonify({
                "modus": "jahr",
                "jahr": jahr,
                "labels": monatsnamen,
                "einspeise": [
                    wert["einspeise"] for wert in monatswerte
                ],
                "gesamt": [
                    wert["gesamt"] for wert in monatswerte
                ],
                "hms": [
                    wert["hms"] for wert in monatswerte
                ],
                "growatt": [
                    wert["growatt"] for wert in monatswerte
                ],
                "solax": [
                    wert["solax"] for wert in monatswerte
                ],
                "solarverbrauch": [
                    wert["solarverbrauch"] for wert in monatswerte
                ],
                "summen": {
                    "einspeise": round(
                        sum(wert["einspeise"] for wert in monatswerte),
                        2,
                    ),
                    "gesamt": round(
                        sum(wert["gesamt"] for wert in monatswerte), 2
                    ),
                    "hms": round(
                        sum(wert["hms"] for wert in monatswerte), 2
                    ),
                    "growatt": round(
                        sum(wert["growatt"] for wert in monatswerte), 2
                    ),
                    "solax": round(
                        sum(wert["solax"] for wert in monatswerte), 2
                    ),
                    "solarverbrauch": round(
                        sum(
                            wert["solarverbrauch"]
                            for wert in monatswerte
                        ),
                        2,
                    ),
                },
            })

        # Monatsansicht
        monat_werte = []
        for wert in tageswerte:
            datum = datetime.strptime(
                wert["datum"], "%d.%m.%y"
            ).date()
            if datum.year == jahr and datum.month == monat:
                monat_werte.append(wert)

        logger.info(
            "[DIAGRAMM] Monat %02d.%s: %s Tage",
            monat, jahr, len(monat_werte)
        )

        # Solarverbrauch pro Tag berechnen
        solarverbrauch = [
            round(
                wert["hms"] + wert["solax"] - wert["einspeise"],
                2,
            )
            for wert in monat_werte
        ]

        return jsonify({
            "modus": "monat",
            "jahr": jahr,
            "monat": monat,
            "labels": [
                wert["datum"] for wert in monat_werte
            ],
            "einspeise": [
                wert["einspeise"] for wert in monat_werte
            ],
            "gesamt": [
                wert["gesamt"] for wert in monat_werte
            ],
            "hms": [
                wert["hms"] for wert in monat_werte
            ],
            "growatt": [
                wert["growatt"] for wert in monat_werte
            ],
            "solax": [
                wert["solax"] for wert in monat_werte
            ],
            "solarverbrauch": solarverbrauch,
            "summen": {
                "einspeise": round(
                    sum(wert["einspeise"] for wert in monat_werte), 2
                ),
                "gesamt": round(
                    sum(wert["gesamt"] for wert in monat_werte), 2
                ),
                "hms": round(
                    sum(wert["hms"] for wert in monat_werte), 2
                ),
                "growatt": round(
                    sum(wert["growatt"] for wert in monat_werte), 2
                ),
                "solax": round(
                    sum(wert["solax"] for wert in monat_werte), 2
                ),
                "solarverbrauch": round(sum(solarverbrauch), 2),
            },
        })

    async def aktuell(self):
        state: AppState = _app_state()
        daten = {}

        for geraet, werte in state.aktuell_werte.items():
            daten[geraet] = [
                {
                    "zeit": datetime.fromtimestamp(zeit).isoformat(
                        timespec="seconds"
                    ),
                    "wert": wert,
                }
                for zeit, wert in werte
            ]

        return jsonify(daten)

    async def api_status(self):
        state: AppState = _app_state()
        # state.last_activity = time.monotonic()
        return jsonify(state.status_html)

    async def log(self):
        return {
            "log": list(log_buffer),
            "level": logging.getLogger().getEffectiveLevel(),
        }

    async def log_level(self):
        state = _app_state()
        data = await request.get_json()
        level = LogManager.normalize_level(
            data.get("level", "INFO")
        )
        LogManager.set_level(level)

        state.log_level = level
        state.einstellungen["log_level"] = level
        await EinstellungenManager.speichere_einstellungen(
            _app_state(), state.einstellungen
        )

        # Meldung nach dem Umschalten erzeugen
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
            "level": level,
        }


# Ein gemeinsamer Manager für alle API-Operationen
api_manager = ApiManager()


# Bestehende Routen bleiben als dünne Aufrufer erhalten

@routes.route("/api/daten")
async def api_daten():
    return await api_manager.daten()


@routes.route("/strom", methods=["GET"])
async def get_strom():
    return await api_manager.strom()


@routes.route("/akku_cloud", methods=["GET"])
def get_akku_cloud():
    return api_manager.akku_cloud()


@routes.route("/hms", methods=["GET"])
def get_hms_800():
    return api_manager.hms()


@routes.route("/solax_cloud", methods=["GET"])
async def get_sol_cloud():
    return await api_manager.solax_cloud()


@routes.route("/solax_local", methods=["GET"])
async def get_local():
    return await api_manager.solax_local()


@routes.route("/parameter", methods=["GET"])
async def get_parameter():
    return await api_manager.parameter()


@routes.route("/parameter_zugang", methods=["GET"])
async def get_parameter_zugang():
    return await api_manager.parameter_zugang()


@routes.route("/status", methods=["GET"])
async def get_latest_status():
    return await api_manager.status()


@routes.route("/tages", methods=["GET"])
async def get_tages():
    return await api_manager.tages()


@routes.route("/roh", methods=["GET"])
def roh():
    return api_manager.roh()


@routes.route("/api/diagramm")
async def api_diagramm():
    return await api_manager.diagramm()


@routes.route("/api/aktuell")
async def api_aktuell():
    return await api_manager.aktuell()


@routes.route("/api/stat")
async def api_status():
    return await api_manager.api_status()


@routes.get("/api/log")
async def api_log():
    return await api_manager.log()


@routes.post("/api/log_level")
async def api_log_level():
    return await api_manager.log_level()
