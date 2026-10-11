from __future__ import annotations
import asyncio
from datetime import datetime
import logging
from typing import Any, Optional, Protocol, TYPE_CHECKING
import tinytuya
from quart import Blueprint, current_app, request
from units.configuration import speichere_einstellungen
from units.calculations import status_aktualisieren, zeitstempel
from units.history import schreibe_in_roh

if TYPE_CHECKING:
    from units.state import AppState

logger = logging.getLogger(__name__)

class DoseDevice(Protocol):
    def status(self) -> Any: ...
    def turn_on(self) -> Any: ...
    def turn_off(self) -> Any: ...
    def set_version(self, version: float) -> Any: ...
    def set_socketTimeout(self, timeout: float) -> Any: ...
    def set_socketRetryLimit(self, limit: int) -> Any: ...

class TuyaDoseManager:

    def __init__(self, app_state: AppState) -> None:
        self.app_state = app_state

    def _create_dose_device(self) -> DoseDevice:
        """Erstellt den tinytuya-Client mit Protokoll-Typ."""
        zugang = self.app_state.zugang
        device_id = zugang.get("dose_device_id", "")
        ip = zugang.get("dose_ip", "192.168.178.41")
        local_key = zugang.get("dose_local_key", "")

        if not device_id or not local_key:
            raise RuntimeError(
                "Tuya-Dose: dose_device_id und dose_local_key fehlen in "
                "data/init_zugang.json."
            )

        device: DoseDevice = tinytuya.OutletDevice(device_id, ip, local_key)
        device.set_version(3.4)
        device.set_socketTimeout(2)
        device.set_socketRetryLimit(1)
        return device

    @property
    def _device(self) -> DoseDevice:
        if self.app_state.dose_device is None:
            logger.info("🔌 Dose nicht initialisiert. Reconnect...")
            self.app_state.dose_device = self._create_dose_device()
        return self.app_state.dose_device

    @_device.setter
    def _device(self, new_device: Optional[DoseDevice]) -> None:
        self.app_state.dose_device = new_device

    def _handle_disconnect(self) -> None:
        logger.warning("🚨 Tuya-Verbindung verloren! Reset für Reconnect...")
        self._device = None

    async def _async_status(self) -> Any:
        try:
            return await asyncio.to_thread(self._device.status)
        except Exception as e:
            logger.error("Fehler beim Status-Abruf: %s", e)
            self._handle_disconnect()
            return None

    async def _async_turn_on(self) -> Any:
        try:
            return await asyncio.to_thread(self._device.turn_on)
        except Exception as e:
            logger.error("Fehler beim Einschalten: %s", e)
            self._handle_disconnect()
            return None

    async def _async_turn_off(self) -> Any:
        try:
            return await asyncio.to_thread(self._device.turn_off)
        except Exception as e:
            logger.error("Fehler beim Ausschalten: %s", e)
            self._handle_disconnect()
            return None

    async def pruefe(self, zeit: float) -> None:
        """Prüft die Dose basierend auf dem definierten Takt-Intervall (wird draußen aufgerufen)."""
        takt = self.app_state.einstellungen.get("takt_dose", 300)
        # Sicherstellen, dass das Attribut auf dem AppState existiert
        if not hasattr(self.app_state, "last_dose_check"):
            self.app_state.last_dose_check = 0.0
        if zeit - self.app_state.last_dose_check > takt:
            try:
                await self.control_loop()
            except Exception:
                logger.exception("[Dose] Fehler in Prüfschleife:")
            finally:
                self.app_state.last_dose_check = zeit

    async def update_status(self) -> Optional[bool]:
        """Ruft den aktuellen Status der Dose ab und aktualisiert den AppState."""
        try:
            data = await self._async_status()
            schreibe_in_roh(self.app_state, "dose", data)
            
            if not data or "dps" not in data:
                logger.error("Dose nicht erreichbar")
                return None
                
            is_on = data["dps"].get("1")
            self.app_state.dose_watt = float(data.get("dps", {}).get("22", 0)) / 10
            takt = self.app_state.einstellungen.get("takt_dose", 300)
            
            self.app_state.alle_daten["dose"]["zeit_meine"] = zeitstempel()
            self.app_state.alle_daten["dose"]["takt_dose"] = takt
            status_aktualisieren(self.app_state, "dose", takt)
            return is_on
        except Exception:
            logger.exception("❌ Dose Fehler beim Status-Abruf:")
            return None

    async def control_loop(self) -> None:
        """Hauptsteuerungslogik für den Automatik-Modus und Not-Aus bei alten Daten."""
        if self.app_state.dose_laeuft:
            return
        self.app_state.dose_laeuft = True
        try:
            is_on = await self.update_status()
            self.app_state.dose_relay_state = is_on
            if is_on is None:
                return

            # Akku-Zeitstempel Validierung
            akku_zeit_str = self.app_state.alle_daten.get("akku", {}).get("zeit_Noah")
            diff_sekunden = 9999
            if akku_zeit_str:
                try:
                    noah_dt = datetime.strptime(akku_zeit_str, "%Y-%m-%d %H:%M:%S")
                    diff_sekunden = (datetime.now() - noah_dt).total_seconds()
                except Exception:
                    logger.exception("❌ Zeit-Fehler:")
            else:
                logger.warning("⚠️ Keine zeit_Noah gefunden")

            if diff_sekunden == 9999:
                logger.info("⚠️ [Dose] - Noch keine Akku-Daten")
                return

            # Sicherheitsabschaltung bei veralteten Daten
            if diff_sekunden > 1200:
                if is_on:
                    logger.info("⚠️ Not-Aus: Akku-Daten sind %s Sek. alt!", int(diff_sekunden))
                    await self.relay_off()
                return

            if self.app_state.dose_mode != "auto":
                return
            # Temperatur-Automatik
            temp = self.app_state.temperature
            t_start = self.app_state.einstellungen.get("dose_t_start", 32)
            t_stop = self.app_state.einstellungen.get("dose_t_stop", 28)

            if temp >= t_start and not is_on:
                await self.relay_on()
            elif temp <= t_stop and is_on:
                await self.relay_off()
        except Exception:
            logger.exception("❌ Dose Fehler in control_loop:")
        finally:
            self.app_state.dose_laeuft = False

    async def relay_on(self) -> None:
        """Schaltet die Steckdose manuell oder automatisch ein."""
        if self.app_state.dose_relay_state is True:
            logger.info("Dose ist bereits An")
            return
        try:
            await self._async_turn_on()
            data = await self._async_status()
            if data and "dps" in data:
                is_on = data["dps"].get("1")
                if is_on is True:
                    logger.info("Dose An ✅")
                    self.app_state.dose_watt = float(data.get("dps", {}).get("22", 0)) / 10
                    self.app_state.dose_relay_state = True
                else:
                    logger.error("❌ Schaltvorgang fehlgeschlagen")
                    self.app_state.dose_relay_state = is_on
            else:
                logger.error("❌ Keine Antwort – Dose offline")
                self.app_state.dose_relay_state = None
        except Exception:
            logger.exception("❌ Fehler beim Einschalten:")
            self.app_state.dose_relay_state = None

    async def relay_off(self) -> None:
        """Schaltet die Steckdose manuell oder automatisch aus."""
        if self.app_state.dose_relay_state is False:
            return
        try:
            await self._async_turn_off()
            data = await self._async_status()
            if data and "dps" in data:
                is_on = data["dps"].get("1")
                self.app_state.dose_relay_state = is_on
                if is_on is False:
                    logger.info("✅ Dose erfolgreich AUS")
                else:
                    logger.warning("Dose ist noch AN – Schaltvorgang fehlgeschlagen")
            else:
                logger.error("❌ Keine Antwort – Dose offline")
                self.app_state.dose_relay_state = None
        except Exception:
            logger.exception("❌ Fehler beim Ausschalten:")
            self.app_state.dose_relay_state = None

    async def shutdown(self) -> bool:
        """Schaltet die Dose beim Herunterfahren aus und prüft den bestätigten Zustand."""
        try:
            await self._async_turn_off()
            data = await self._async_status()
            if data and "dps" in data and data["dps"].get("1") is False:
                self.app_state.dose_relay_state = False
                logger.info("✅ Not-Aus: Dose ausgeschaltet und Status bestätigt.")
                return True

            self.app_state.dose_relay_state = (
                data.get("dps", {}).get("1") if data and "dps" in data else None
            )
            logger.error("❌ Not-Aus: Ausschalten konnte nicht bestätigt werden.")
            return False
        except Exception:
            self.app_state.dose_relay_state = None
            logger.exception("❌ Not-Aus: Dose konnte nicht ausgeschaltet werden.")
            return False


# --- Quart Web-Interface Blueprint ---
bp = Blueprint("dose", __name__, url_prefix="/dose")

def _get_manager() -> TuyaDoseManager:
    """Hilfsfunktion, um den Manager direkt aus dem Quart-Context zu ziehen."""
    app_state: AppState = current_app.extensions["app_state"]
    return app_state._dose_manager  # type: ignore

@bp.route("/set_mode", methods=["POST"])
async def set_mode():
    manager = _get_manager()
    data = await request.form
    mode = data.get("mode", "manual")
    manager.app_state.dose_mode = mode
    return "", 204

@bp.route("/manual", methods=["POST"])
async def manual():
    manager = _get_manager()
    form_data = await request.form
    if form_data.get("action") == "on":
        await manager.relay_on()
    else:
        await manager.relay_off()
    return "", 204

@bp.route("/set_temps", methods=["POST"])
async def set_temps():
    manager = _get_manager()
    data = await request.form
    try:
        start = int(data.get("start", 32))
        stop = int(data.get("stop", 28))
    except ValueError:
        return "Ungültige Werte", 400
    
    if not 20 <= start <= 45:
        return "Start muss zwischen 20 und 45°C liegen", 400
    if stop > start - 1:
        return "Stop muss mindestens 1°C kleiner als Start sein", 400
    if stop < 0:
        return "Stop darf nicht negativ sein", 400

    manager.app_state.einstellungen["dose_t_start"] = start
    manager.app_state.einstellungen["dose_t_stop"] = stop
    
    await speichere_einstellungen(manager.app_state, manager.app_state.einstellungen)
    await manager.control_loop()
    return "", 204
