"""Settings routes."""
import asyncio
from . import routes, _app_state
from quart import current_app, flash, jsonify, redirect, render_template, request
from units.funkzii import sende_vdazu_tasmota, speichere_einstellungen, speichere_zugang
from units.funkzii2 import get_web_daten
from units.growatt import GrowattSessionManager
from units.logic import get_nachtzeten, rechne_dazu
from units.state import AppState
import time
import logging
logger = logging.getLogger(__name__)


async def _stop_server_after_response(
    shutdown_event: asyncio.Event,
    delay: float = 0.5,
) -> None:
    await asyncio.sleep(delay)
    shutdown_event.set()


@routes.post("/shutdown")
async def shutdown_server():
    shutdown_event = current_app.extensions.get("server_shutdown_event")
    if shutdown_event is None:
        return jsonify({"success": False, "message": "Server-Abschaltung ist nicht verfügbar."}), 503

    current_app.add_background_task(
        _stop_server_after_response,
        shutdown_event,
        5,
    )
    return await render_template("shutdown.html"), 202


@routes.route("/update_einstellung", methods=["POST"])
async def update_einstellung():
    state: AppState = _app_state()
    try:
        # Daten vom Übernehmen-Button (JSON Paket)
        data = await request.get_json()  
        mapping = {
            "switchNulleinspeisung": "nur_nulleinspeisung",
            "switchSanft": "akku_sanft",
            "switchSanftZeit": "akku_sanft_zeit",
            "switchPPV": "akku_ppv",
            "switchHart": "akku_entladen",
            "switchNacht": "nacht_nur_0_schalter",

        }
        state.takt_geaendert = True 
        # Wir gehen alle gesendeten IDs durch und speichern sie im State
        if data:
            for sid, status in data.items():
                if sid in mapping:
                    key = mapping[sid]
                    state.einstellungen[key] = status
            # Alles dauerhaft in die Datei schreiben
            await speichere_einstellungen(_app_state(), state.einstellungen)
            await rechne_dazu(_app_state())     #  auch mit smart sinchton           
            return jsonify({"success": True,
                            "nacht_nur_0_schalter": state.einstellungen.get('nacht_nur_0_schalter', False)})       
        return jsonify({"success": False, "error": "Keine Daten empfangen"}), 400
    except Exception as e:
        logger.exception("!!! FEHLER IN ROUTE: ")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/update_soc", methods=["POST"])
async def update_soc():
    state: AppState = _app_state()
    try:
        data = await request.get_json()
        field = data.get("id")
        value = int(data.get("value", 0))

        if field not in ["dischargeSocLimit", "chargeSocLimit"]:
            return jsonify({"error": "Ungültiges Feld"}), 400
        results = []
        if field == "chargeSocLimit":
            # Max 
            soc_ist = state.alle_daten["akku"].get("chargeSocLimit", 0)

            if value != soc_ist:
                res_max = await state.growatt.run_with_lock(
                    state.growatt.set_limit_soc,
                    "max",
                    value,
                    soc_ist,
                    min_v=70,
                    max_v=100,
                    cooldown=0
                )
                if res_max and res_max.get("result") == 0:
                    results.append(res_max)
                else:
                    return jsonify({
                        "error": res_max.get(
                            "message",
                            "Max SOC konnte bei Growatt nicht gesetzt werden"
                        )
                    }), 500
        if field == "dischargeSocLimit":
            # Min SOC
            soc_ist = state.alle_daten["akku"].get("dischargeSocLimit", 0)
            if value != soc_ist:
                res_min = await state.growatt.run_with_lock(
                    state.growatt.set_limit_soc,
                    "min",
                    value,
                    soc_ist,
                    min_v=1,
                    max_v=30,
                    cooldown=0
                )
                if res_min and res_min.get("result") == 0:
                    results.append(res_min)
                else:
                    return jsonify({
                        "error": res_min.get(
                            "message",
                            "Min SOC konnte bei Growatt nicht gesetzt werden"
                        )
                    }), 500
        # Erst nach erfolgreichem Setzen speichern
        state.einstellungen[field] = value
        await speichere_einstellungen(_app_state(), state.einstellungen)
        logger.info("[SOC] RESULTS: %r", results)
        logger.info("[SOC] TYPE: %s", type(results))
        return jsonify(results)
    except Exception as e:
        logger.exception("[SOC] Fehler")

@routes.route("/zugang", methods=["GET", "POST"])
async def zugang():
    state: AppState = _app_state()
    if request.method == "POST":
        app_state = state
        form = await request.form
        for key, old_value in state.zugang.items():
             value = form.get(key)
             if value is None:
                 continue
             if isinstance(old_value, int):
               try:
                    state.zugang[key] = int(value)
               except ValueError:
                    pass          # alten Wert behalten
             elif isinstance(old_value, float):
                 try:
                    state.zugang[key] = float(value)
                 except ValueError:
                    pass
             else:
                state.zugang[key] = value
        await speichere_zugang(_app_state(), state.zugang)
        
# Alte Session schließen, falls schon existiert
        if hasattr(state, "growatt") and state.growatt.session:
            await state.growatt.close()
# Growatt-Session neu erzeugen
        app_state.growatt = GrowattSessionManager(
            state.zugang["username"],
            state.zugang["password"],
            state.zugang["deviceSn"],
            state.zugang["token"],
            app_state=app_state,
        )
        await app_state.growatt.init_session()  # Session öffnen          
        return redirect("/zugang")

    return await render_template(
        "zugang.html",
        zugang=state.zugang 
    )

@routes.route("/einstellungen")
async def einstellungen_seite():
    state: AppState = _app_state()
    return await render_template("einstellungen.html", 
                                 einstellungen=state.einstellungen, 
                                 daten=state.alle_daten,
                                 web=get_web_daten(_app_state())
    )

@routes.route("/update", methods=["POST"])
async def update_settings():
    state: AppState = _app_state()
    form = await request.form
    state.einstellungen["nacht_nur_0_schalter"] = "true" in form.getlist("nacht_nur_0_schalter")
    state.takt_geaendert = True   # um zu aktualiesiren
# Korrekturzeiten: 60 Minuten nach Sonnenaufgang / 60 Minuten vor Sonnenuntergang
    try:
       state.einstellungen["kor_aufgang"] = int(form.get("kor_aufgang", 60))
    except ValueError:
       state.einstellungen["kor_aufgang"] = 60
    try:
       state.einstellungen["kor_unter"] = int(form.get("kor_unter", 60))
    except ValueError:
       state.einstellungen["kor_unter"] = 60
    get_nachtzeten(_app_state())

# Sicheres Parsen der Checkbox (immer vorhanden durch hidden input)
    state.einstellungen["akku_entladen"] = "true" in form.getlist("akku_entladen")
    state.einstellungen["abfrage_growatt"] = form.get("abfrage_growatt") == "true"
    state.einstellungen["abfrage_tasmota"] = form.get("abfrage_tasmota") == "true"

    hms_bekommt_null = "true" in form.getlist("hms_bekommt_null")
    hms_hat = state.einstellungen.get("hms_bekommt_null",False)
    #    wenn ungleich
    if hms_bekommt_null  ^ hms_hat: 
        if   hms_bekommt_null:
            state.start_hms0 = 0
        else: 
            logger.info("HMS Limit  auf 0 AUS)")
        state.einstellungen["hms_bekommt_null"] = hms_bekommt_null
        await sende_vdazu_tasmota(_app_state(), 0)

    state.hms_bekommt_null =  state.einstellungen.get("hms_bekommt_null",False)
    
    state.einstellungen["akku_sanft"] = "true" in form.getlist("akku_sanft")
    state.akku_sanft_zeit = "true" in form.getlist("akku_sanft_zeit")

    state.einstellungen["akku_ppv"] = "true" in form.getlist("akku_ppv")
    state.einstellungen["solax_l_mittelwert_nutzen"] = "true" in form.getlist("solax_l_mittelwert_nutzen")
    state.einstellungen["nachricht_app"] = "true" in form.getlist("nachricht_app")
# Taktzeiten
    state.einstellungen["takt_benutzrer_activ"] = int(form.get("takt_benutzrer_activ", 50))
    state.einstellungen["takt_hms"] = int(form.get("takt_hms", 25))
    state.einstellungen["takt_akku"] = int(form.get("takt_akku", 25))
    state.einstellungen["takt_akku_inactiv"] = int(form.get("takt_akku_inactiv", 60))
    state.einstellungen["takt_solax_l"] = int(form.get("takt_solax_l", 25))
    state.einstellungen["takt_solax_c"] = int(form.get("takt_solax_c", 25))
    state.einstellungen["takt_strom"] = int(form.get("takt_strom", 25))
    state.einstellungen["intervall_takt"] = int(form.get("intervall_takt", 4))
    # Zahleneingaben mit Fallbacks absichern
    try:
        state.einstellungen["hms_limit_soll"] = int(form.get("hms_limit_soll", 100))
        state.einstellungen["ppv_soc_ab"] = int(form.get("ppv_soc_ab", 55))
        state.einstellungen["max_limit"] = int(form.get("max_limit", 750))
        state.einstellungen["max_soc"] = int(form.get("max_soc", 99)) 
        state.einstellungen["watt_max"] = int(form.get("watt_max", 4000))
        state.einstellungen["sanft_soc_meher"] = int(form.get("sanft_soc_meher", 11))
        state.einstellungen["dazu_tolleranz"] = int(form.get("dazu_tolleranz", 20))         
        state.einstellungen["dazu_senden"] = int(form.get("dazu_senden", 180))
        state.einstellungen["dazu_sanft"] = int(form.get("dazu_sanft", 0))
        state.dazu_intervall = float(form.get("dazu_intervall", 0))

        if state.dazu_intervall > 0: 
            state.bool_dazu_intervall = True
            state.dazu_intervall_dauer = state.dazu_intervall  # z. B. 5 Minuten
            state.dazu_intervall_start = time.monotonic()
            state.dazu_intervall_ende  = time.monotonic() + state.dazu_intervall    
        else:    
            state.bool_dazu_intervall = False 
            state.akku_sanft_zeit = False
            state.dazu_intervall = 0.0
    except ValueError as e:
        flash(f"Ungültige Eingabe: {e}")
        return jsonify({"success": False, "message": f"Ungültige Eingabe: {e}"}) 
    try:
       state.einstellungen["mittel_verbrauch"] = int(form.get("mittel_verbrauch", 100))
    except ValueError as e:
       flash(f"Ungültige Eingabe bei Akku-Parametern: {e}")
       return jsonify({"success": False, "message": f"Ungültige Eingabe bei Akku-Parametern: {e}"})

    await speichere_einstellungen(_app_state(), state.einstellungen)
    await rechne_dazu(_app_state())     #  auch mit smart sinchton

    # JSON zurückgeben, damit der Browser die Toasts anzeigen kann
    return jsonify({
        "success": True,
        "message": "Einstellungen wurden erfolgreich gespeichert!"
    })

@routes.route("/api/toggle_aktuell", methods=["POST"])
async def toggle_aktuell():
    state: AppState = _app_state()
    data = await request.get_json()
    status = bool(data.get("aktuell_aktiv", True))
    state.einstellungen["aktuell_aktiv"] = status
    logger.info("Daten 48h Speicherng: %s",status)
    state.takt_geaendert =True
    await speichere_einstellungen(_app_state(), state.einstellungen)
    return jsonify({
        "aktuell_aktiv": status
    })
