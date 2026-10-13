import asyncio
import logging
import aiohttp
from units.calculations import StatusManager, ZeitstempelManager
from units.configuration import mache_session
from units.history import get_history_manager

logger = logging.getLogger(__name__)

class Strom:
    def __init__(self, app_state):
        self.app_state = app_state

    async def abfrage_tasmota(
        self,
        alt_daten: dict,
        takt: int = 5,
    ) -> dict:
        app_state = self.app_state
        ip = app_state.zugang.get("ip_tasmota")
        ip_haupt = app_state.zugang.get("ip_haupt")
        url_end = app_state.zugang.get("url_tasmota")
        url = f"{ip_haupt}{ip}{url_end}"
        session = await mache_session(app_state, "session_tasmota")
        fehler = None
        try:
            async with session.get(url, timeout=5) as response:
                response.raise_for_status()
                json_data = await response.json()
                get_history_manager(app_state).schreibe_in_roh("tasmota", json_data)
                status_sns = json_data.get("StatusSNS", {})
                smart_meter = status_sns.get("SM", {})
                if not smart_meter:
                    logger.error(
                        "[Tasmota] Warnung: keine daten "
                        "'SM' Datenpfad nicht gefunden"
                    )

                await self.vergleiche_hms0(status_sns.get("hms0", 1))
                result = {
                    "Gesamt": smart_meter.get("Gesamt", 0.0),
                    "Einspeise": smart_meter.get("Einspeise", 0.0),
                    "Actuel": smart_meter.get("Actuel", 0.0),
                    "V1": smart_meter.get("V1", 0.0),
                    "V2": smart_meter.get("V2", 0.0),
                    "V3": smart_meter.get("V3", 0.0),
                    "vdazu": status_sns.get("vdazu", 0),
                    "takt": takt,
                    "zeit_meine": ZeitstempelManager.zeitstempel(),
                }
                StatusManager.status_aktualisieren(app_state, "strom", takt)
                logger.info("Tasmota Aufruf✅ %s Sek", takt)
                logger.debug("Daten %s", result)
                return result
        except asyncio.TimeoutError:
            fehler = "Timeout"
            logger.warning("[Tasmota] Timeout")
        except aiohttp.ClientError as error:
            fehler = str(error)
            logger.warning("[Tasmota] HTTP-Fehler: %s", error)
        except Exception:
            logger.exception("[Tasmota] Unerwarteter Fehler")
            fehler = "Unbekannter Fehler"

        result = (alt_daten or {}).copy()
        result.update({
            "fehler": fehler or "Unbekannter Fehler",
            "zeit_fehler": ZeitstempelManager.zeitstempel(),
        })
        return result

    async def abfrage_smart(
        self,
        alt_daten: dict,
        ip_smart: str = "123",
        takt: int = 4,
        versuche: int = 3,
        basis_wartezeit: int = 2,
    ) -> dict:
        app_state = self.app_state
        session = await mache_session(app_state, "session_strom")
        url = f"{app_state.zugang.get('ip_haupt')}{ip_smart}/smartdaten"
        for versuch in range(versuche):
            try:
                async with session.get(url, timeout=5) as response:
                    response.raise_for_status()
                    data = await response.json()
                    data["takt"] = takt
                    data["zeit_meine"] = ZeitstempelManager.zeitstempel()
                    StatusManager.status_aktualisieren(app_state, "strom", takt)
                    logger.info("[Strom] OK bei Versuch %s", versuch + 1)
                    return data
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                logger.warning(
                    "[Strom] Verbindungsproblem Versuch %s: %s",
                    versuch + 1,
                    error,
                )
            except Exception:
                logger.exception("[Strom] Unerwarteter Fehler:")
                break
            if versuch < versuche - 1:
                await asyncio.sleep(basis_wartezeit * (2 ** versuch))

        result = (alt_daten or {}).copy()
        result.update({
            "fehler": f"Strom API {url} nicht erreichbar",
            "zeit_fehler": ZeitstempelManager.zeitstempel(),
        })
        logger.error("[Strom] Alle Versuche fehlgeschlagen. Rückfall auf alt_daten.")
        return result

    async def sende_tasmota(
        self,
        vdazu_wert: int,
        timeout_sek: int = 5,
    ) -> dict:
        app_state = self.app_state
        session = await mache_session(app_state, "session_strom")
        lan_ip = app_state.zugang["ip_tasmota"]
        soc = app_state.soc
        ppv = app_state.alle_daten.get("akku", {}).get("ppv", 0) or 0
        hms = app_state.alle_daten.get("hms", {}).get("aktuell", 0) or 0
        solax = app_state.alle_daten.get("solax", {}).get("acpower", 0) or 0
        haus = StatusManager.haus_verbrauch_get(app_state)
        nullen = app_state.einstellungen.get("hms_bekommt_null", False)
        hms0 = 0 if nullen else 1
        url = (
            f"{app_state.zugang.get('ip_haupt')}{lan_ip}/cm?cmnd=script+%3E"
            f"time=600;"
            f"vdazu={vdazu_wert};"
            f"solax={solax};"
            f"soc={soc};"
            f"haus={haus};"
            f"ppv={ppv};"
            f"hms={hms};"
            f"hms0={hms0}"
        )
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout_sek),
            ) as response:
                response.raise_for_status()
                html = await response.text()
                logger.debug("Tasmota Send-Antwort: %s", html)
                logger.info("Tasmota senden ✅ ")
                return {
                    "status": "OK",
                    "ip": lan_ip,
                    "wert": vdazu_wert,
                    "html": html,
                }
        except asyncio.TimeoutError:
            logger.warning("[Tasmota] Timeout beim Senden an %s", url)
            return {"error": f"Timeout beim Senden an {url}"}
        except aiohttp.ClientError as error:
            logger.error("[Tasmota] HTTP-Fehler: %s", error)
            return {"error": f"HTTP-Fehler: {error}"}
        except Exception:
            logger.exception("[Tasmota] Allgemeiner Fehler")
            return {"error": "Allgemeiner Fehler"}

    async def sende_smart(
        self,
        vdazu_wert: int,
        timeout_sek: int = 5,
    ) -> dict:
        app_state = self.app_state
        session = await mache_session(app_state, "session_strom")
        lan_ip = app_state.zugang["ip_smart"]
        url = (
            f"{app_state.zugang.get('ip_haupt')}{lan_ip}"
            f"/send_dazu?vdazu={vdazu_wert}"
        )
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout_sek),
            ) as response:
                response.raise_for_status()
                html = await response.text()
                return {
                    "status": "OK",
                    "ip": lan_ip,
                    "wert": vdazu_wert,
                    "html": html,
                }
        except asyncio.TimeoutError:
            logger.warning("[Smart] Timeout beim Senden an %s", url)
            return {"error": f"Timeout beim Senden an {url}"}
        except aiohttp.ClientError as error:
            logger.error("[Smart] HTTP-Fehler: %s", error)
            return {"error": f"HTTP-Fehler: {error}"}
        except Exception:
            logger.exception("[Smart] Allgemeiner Fehler")
            return {"error": "Allgemeiner Fehler"}

    async def vergleiche_hms0(self, hms0) -> None:
        app_state = self.app_state
        nullung = app_state.einstellungen.get("hms_bekommt_null", False)
        if (nullung and hms0 == 0) or (not nullung and hms0 == 1):
            return
        await self.sende_tasmota(0)
        logger.info("An Tasmota senden %s= %s", nullung, hms0)

    @property
    def takt(self) -> int:
        einst = self.app_state.einstellungen
        if self.app_state.benutzer_activ:
            return einst.get("takt_strom", 15)
        
        takt = einst.get("takt_akku_inactiv", 120)
        if self.app_state.nachtzeit and not self.app_state.benutzer_activ:
            takt = einst.get("takt_cloud_nacht", 600)
        if einst.get("aktuell_aktiv", False):
            takt = self.app_state.takt_48
        return takt

    
    async def pruefe(self, zeit: float) -> None:
        app_state = self.app_state
        takt = self.takt
        StatusManager.status_aktualisieren(app_state, "strom", takt,False)
        if zeit - app_state.start_strom <= takt and not app_state.erste_abfrage:
            return
        logger.debug("Strom %s Sek", takt)
        try:
            if app_state.einstellungen.get("abfrage_tasmota", False):
                strom = await self.abfrage_tasmota(
                    app_state.alle_daten.get("strom") or {},
                    takt)
            else:
                strom = await self.abfrage_smart(
                    app_state.alle_daten.get("strom") or {},
                    app_state.zugang.get("ip_smart", "123"),
                    takt)
            app_state.alle_daten["strom"] = strom
            if app_state.einstellungen.get("aktuell_aktiv", True):
                get_history_manager(app_state).speichere_aktuell_wert("strom",strom.get("Actuel", 0),)
        except Exception:
            logger.exception("[Fehler] ❌ Stromabfrage fehlgeschlagen")
        finally:
            app_state.start_strom = zeit
