from units.state import AppState
import json
import aiohttp
from units.funkzii import (
   mache_session
)
import logging
logger = logging.getLogger(__name__)

async def lese_hms_powerlimiter(app_state: AppState) -> dict:
    # Aufruf: daten = await lese_hms_powerlimiter(app_state)
    try:
        dtu_ip = (
            f"{app_state.zugang.get('ip_haupt')}"
            f"{app_state.zugang.get('ip_hms')}"
        )
        url = f"{dtu_ip}/api/powerlimiter/config"
        auth = aiohttp.BasicAuth(
            app_state.zugang.get("hms_name"),
            app_state.zugang.get("hms_pas")
        )
        session = await mache_session(app_state, "session_hms",auth=auth)
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=5)
        ) as response:
            response.raise_for_status()
            config = await response.json()
            logger.info("[DPL] OpenDTU PowerLimiter: %s",config)
            return config
    except Exception:
        logger.exception(
            "[DPL] Fehler beim Auslesen des PowerLimiters"
        )
        return {}

async def setze_hms_powerlimiter(app_state: AppState, aktiv: bool) -> bool:
    try:
        # Aktuelle Konfiguration über vorhandene Funktion holen
        config = await lese_hms_powerlimiter(app_state)
        if not config:
            logger.warning("[DPL] Keine PowerLimiter-Konfiguration erhalten.")
            return False
        # Nur AN/AUS ändern
        if config.get("enabled") != bool(aktiv):
            config["enabled"] = bool(aktiv)
        else:
           logger.info("[DPL] PowerLimiter bereits %s","AN" if aktiv else "AUS")
           return True
        dtu_ip = (
            f"{app_state.zugang.get('ip_haupt')}"
            f"{app_state.zugang.get('ip_hms')}"
        )
        url = f"{dtu_ip}/api/powerlimiter/config"
        auth = aiohttp.BasicAuth(
            app_state.zugang.get("hms_name"),
            app_state.zugang.get("hms_pas")
        )
        session = await mache_session(app_state, "session_hms",auth=auth)
        # Komplette vorhandene Konfiguration zurückschreiben
        async with session.post(
            url,
            data={"data": json.dumps(config)},
            timeout=aiohttp.ClientTimeout(total=5)
        ) as response:
            response.raise_for_status()
            ergebnis = await response.json()
        if ergebnis.get("type") == "success":
            logger.info(
                "[DPL] PowerLimiter %s",
                "AN" if aktiv else "AUS"
            )
            return True
        logger.warning( "[DPL] Änderung nicht übernommen: %s",ergebnis)
        return False
    except Exception:
        logger.exception("[DPL] Fehler beim Umschalten des PowerLimiters")
        return False

async def lese_hms_powerlimiter_status(app_state: AppState) -> dict:
    try:
        dtu_ip = (
            f"{app_state.zugang.get('ip_haupt')}"
            f"{app_state.zugang.get('ip_hms')}"
        )
        url = f"{dtu_ip}/api/powerlimiter/status"
        auth = aiohttp.BasicAuth(
            app_state.zugang.get("hms_name"),
            app_state.zugang.get("hms_pas")
        )
        session = await mache_session(
            app_state,
            "session_hms",
            auth=auth
        )
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=5)
        ) as response:
            response.raise_for_status()
            daten = await response.json()
            logger.info(
                "[DPL] PowerLimiter Status: %s",
                daten
            )
            return daten

    except Exception:
        logger.exception(
            "[DPL] Fehler beim Auslesen des PowerLimiter Status"
        )
        return {}

async def schalte_hms_wr(app_state: AppState, aktiv: bool) -> bool:
    try:
        hms = app_state.alle_daten.get("hms", {})
        serial = hms.get("serial", "")
        producing = hms.get("producing", False)
        reachable = hms.get("reachable", False)
        if not serial:
            logger.warning("[HMS] Keine Seriennummer vorhanden.")
            return False
        logger.info(
            "[HMS] WR Status: reachable=%s, producing=%s",
            reachable,
            producing
        )
        # Bereits im gewünschten Zustand
        if aktiv and producing:
            logger.info("[HMS] WR ist bereits AN.")
            return True
        if not aktiv and not producing:
            logger.info("[HMS] WR ist bereits AUS.")
            return True
        # Nicht erreichbar -> nicht blind schalten
        if not reachable:
            logger.warning(
                "[HMS] WR nicht erreichbar - kein Schaltbefehl."
            )
            return False
        dtu_ip = (
            f"{app_state.zugang.get('ip_haupt')}"
            f"{app_state.zugang.get('ip_hms')}"
        )
        url = f"{dtu_ip}/api/power/config"
        payload = {
            "serial": serial,
            "power": bool(aktiv)
        }
        auth = aiohttp.BasicAuth(
            app_state.zugang.get("hms_name"),
            app_state.zugang.get("hms_pas")
        )
        session = await mache_session(
            app_state,
            "session_hms",
            auth=auth
        )
        async with session.post(
            url,
            data={"data": json.dumps(payload)},
            timeout=aiohttp.ClientTimeout(total=5)
        ) as response:
            text = await response.text()
            logger.info(
                "[HMS] WR %s HTTP %s: %s",
                "AN" if aktiv else "AUS",
                response.status,
                text
            )
            return response.status < 400
    except Exception:
        logger.exception(
            "[HMS] Fehler beim Schalten des WR"
        )
        return False
    
'''
DPL
    {'enabled': False, 
    'solar_passthrough_enabled': False, 
    'conduction_losses': 0, 
    'battery_always_use_at_night': False,
    'target_power_consumption': -5, 
    'target_power_consumption_hysteresis': 15,
    'base_load_limit': 200, 'ignore_soc': True,
    'battery_soc_start_threshold': 80, 
    'battery_soc_stop_threshold': 20, 
    'voltage_start_threshold': 50, 
    'voltage_stop_threshold': 49,
    'voltage_load_correction_factor': 0.001, 
    'full_solar_passthrough_soc': 100, 
    'full_solar_passthrough_start_voltage': 66,
    'full_solar_passthrough_stop_voltage': 66,
    'inverter_serial_for_dc_voltage': '114491514518', 
    'inverter_channel_id_for_dc_voltage': 0,
                  'inverter_restart_hour': 0, 
    'total_upper_power_limit': 800, 
                  'inverters': [{'serial': '114491514518', 
    'is_governed': True, 'is_behind_power_meter': True,
      'power_source': 2,
        'use_overscaling_to_compensate_shading': True,
          'allow_standby': False,
            'lower_power_limit': 26,
    'upper_power_limit': 800}]}

'''