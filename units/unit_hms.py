import asyncio
import json
import logging
import aiohttp
from units.unit_alle.calculations import status_aktualisieren, zeitstempel
from units.unit_alle.configuration import mache_session
from units.unit_alle.history import schreibe_in_roh
from units.unit_alle.history import speichere_aktuell_wert
from units.state import AppState

logger = logging.getLogger(__name__)

class Hms:
    def __init__(self, app_state):
        self.app_state = app_state

    async def abfrage(
        self,
        alt_daten: dict,
        takt: int,
        versuche: int = 3,
        basis_wartezeit: int = 2,
    ) -> dict:
        app_state = self.app_state
        url = (
            f"{app_state.zugang.get('ip_haupt')}"
            f"{app_state.zugang.get('ip_hms')}"
            "/api/livedata/status/inverters"
        )
        auth = aiohttp.BasicAuth(
            app_state.zugang.get("hms_name"),
            app_state.zugang.get("hms_pas"),
        )
        session = await mache_session(app_state, "session_hms", auth=auth)
        for versuch in range(versuche):
            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    schreibe_in_roh(app_state, "hms", data)
                    total = data.get("total", {})
                    inverters = data.get("inverters", [])
                    inverter = inverters[0] if inverters else {}
                    result = {
                        "heute": total.get("YieldDay", {}).get("v", 0),
                        "gesamt": total.get("YieldTotal", {}).get("v", 0),
                        "aktuell": total.get("Power", {}).get("v", 0),
                        "limit": inverter.get("limit_absolute", 0),
                        "producing": inverter.get("producing", False),
                        "reachable": inverter.get("reachable", False),
                        "takt": takt,
                        "serial": inverter.get("serial", ""),
                        "zeit_meine": zeitstempel(),
                    }
                    status_aktualisieren(app_state, "hms", takt)
                    return result
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                logger.warning(
                    "[HMS] Verbindungsproblem Versuch %s: %s",
                    versuch + 1,
                    error,
                )
            except Exception:
                logger.exception("[HMS] Unerwarteter Fehler:")
                break

            if versuch < versuche - 1:
                await asyncio.sleep(basis_wartezeit * (2 ** versuch))

        result = (alt_daten or {}).copy()
        result.update({
            "fehler": "HMS API nicht erreichbar",
            "zeit_fehler": zeitstempel(),
        })
        logger.error("[HMS] Alle Versuche fehlgeschlagen.")
        return result

    async def setze_limit(self, limit_watt: int) -> bool:
        app_state = self.app_state
        try:
            limit_watt = int(limit_watt)
            dtu_ip = (
                f"{app_state.zugang.get('ip_haupt')}"
                f"{app_state.zugang.get('ip_hms')}"
            )
            serial = app_state.alle_daten.get("hms", {}).get("serial", "")
            if not serial:
                logger.warning("[HMS] Keine Seriennummer für OpenDTU vorhanden.")
                return False
            url = f"{dtu_ip}/api/limit/config"
            payload = {
                "serial": serial,
                "limit_type": 0,
                "limit_value": limit_watt,
            }
            session = await mache_session(
                app_state,
                "session_hms",
                auth=aiohttp.BasicAuth(
                    app_state.zugang.get("hms_name"),
                    app_state.zugang.get("hms_pas"),
                ),
            )
            async with session.post(
                url,
                data={"data": json.dumps(payload)},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                response.raise_for_status()
                result = await response.json()
                if result.get("type") == "success":
                    logger.info(
                        "[HMS] OpenDTU Limit %s W gesendet: %s",
                        limit_watt,
                        result,
                    )
                    app_state.alle_daten.setdefault("hms", {})[
                        "limit"
                    ] = limit_watt
                    return True
                logger.warning("[HMS] Limit nicht übernommen: %s", result)
                return False
        except Exception:
            logger.exception("[HMS] Fehler beim Setzen des Limits")
            return False

    async def pruefe(self, zeit: float) -> None:
        app_state = self.app_state
        takt=self.takt
        if zeit - app_state.start_hms > takt or app_state.erste_abfrage:
            logger.info("📡 HMS✅ %s Sek", takt)
            app_state.alle_daten["hms"] = await self.abfrage(
                app_state.alle_daten.get("hms", {}),
                takt
            )
            app_state.start_hms = zeit
            if app_state.einstellungen.get("aktuell_aktiv", True):
                speichere_aktuell_wert(
                    app_state,
                    "hms",
                    app_state.alle_daten["hms"].get("aktuell", 0)
                )

    async def pruefe_limit(self, zeit: float, nullen: bool) -> None:
        app_state = self.app_state
        if app_state.start_hms0 < 2:
            app_state.start_hms0 += 1
            logger.info(
                "⏳ HMS-Limit: %s Takt Startverzögerung",
                app_state.start_hms0
            )
            return
        if nullen:
            hms_limit_soll = int(
                app_state.einstellungen.get("hms_limit_soll", 100)
            )
            hms_limit_aktuell = (
                app_state.alle_daten.get("hms", {}).get("limit", 0)
            )
            if abs(hms_limit_aktuell - hms_limit_soll) > 10:
                if await self.setze_limit(hms_limit_soll):
                    logger.info(
                        "HMS neues Limit: %s W (vorher %s W)",
                        hms_limit_soll,
                        hms_limit_aktuell
                    )

    async def lese_config(self) -> dict:
        app_state = self.app_state
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
            session = await mache_session(
                app_state,
                "session_hms",
                auth=auth,
            )
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                response.raise_for_status()
                config = await response.json()
                logger.info("[DPL] OpenDTU PowerLimiter: %s", config)
                return config
        except Exception:
            logger.exception("[DPL] Fehler beim Auslesen des PowerLimiters")
            return {}

    async def setze_powerlimiter(self, aktiv: bool) -> bool:
        app_state = self.app_state
        try:
            config = await self.lese_config()
            if not config:
                logger.warning(
                    "[DPL] Keine PowerLimiter-Konfiguration erhalten."
                )
                return False
            if config.get("enabled") != bool(aktiv):
                config["enabled"] = bool(aktiv)
            else:
                logger.info(
                    "[DPL] PowerLimiter bereits %s",
                    "AN" if aktiv else "AUS",
                )
                return True
            dtu_ip = (
                f"{app_state.zugang.get('ip_haupt')}"
                f"{app_state.zugang.get('ip_hms')}"
            )
            url = f"{dtu_ip}/api/powerlimiter/config"
            auth = aiohttp.BasicAuth(
                app_state.zugang.get("hms_name"),
                app_state.zugang.get("hms_pas"),
            )
            session = await mache_session(
                app_state,
                "session_hms",
                auth=auth,
            )
            async with session.post(
                url,
                data={"data": json.dumps(config)},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                response.raise_for_status()
                ergebnis = await response.json()
            if ergebnis.get("type") == "success":
                logger.info(
                    "[DPL] PowerLimiter %s",
                    "AN" if aktiv else "AUS",
                )
                return True
            logger.warning("[DPL] Änderung nicht übernommen: %s", ergebnis)
            return False
        except Exception:
            logger.exception("[DPL] Fehler beim Umschalten des PowerLimiters")
            return False

    async def lese_powerlimiter_status(self) -> dict:
        app_state = self.app_state
        try:
            dtu_ip = (
                f"{app_state.zugang.get('ip_haupt')}"
                f"{app_state.zugang.get('ip_hms')}"
            )
            url = f"{dtu_ip}/api/powerlimiter/status"
            auth = aiohttp.BasicAuth(
                app_state.zugang.get("hms_name"),
                app_state.zugang.get("hms_pas"),
            )
            session = await mache_session(
                app_state,
                "session_hms",
                auth=auth,
            )
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                response.raise_for_status()
                daten = await response.json()
                logger.info("[DPL] PowerLimiter Status: %s", daten)
                return daten
        except Exception:
            logger.exception(
                "[DPL] Fehler beim Auslesen des PowerLimiter Status"
            )
            return {}

    async def schalte_wr(self, aktiv: bool) -> bool:
        app_state = self.app_state
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
                producing,
            )
            if aktiv and producing:
                logger.info("[HMS] WR ist bereits AN.")
                return True
            if not aktiv and not producing:
                logger.info("[HMS] WR ist bereits AUS.")
                return True
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
            payload = {"serial": serial, "power": bool(aktiv)}
            auth = aiohttp.BasicAuth(
                app_state.zugang.get("hms_name"),
                app_state.zugang.get("hms_pas"),
            )
            session = await mache_session(
                app_state,
                "session_hms",
                auth=auth,
            )
            async with session.post(
                url,
                data={"data": json.dumps(payload)},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                text = await response.text()
                logger.info(
                    "[HMS] WR %s HTTP %s: %s",
                    "AN" if aktiv else "AUS",
                    response.status,
                    text,
                )
                return response.status < 400
        except Exception:
            logger.exception("[HMS] Fehler beim Schalten des WR")
            return False



    @property
    def takt(self) -> int:
        einst = self.app_state.einstellungen
        # 1. Benutzer ist aktiv
        if self.app_state.benutzer_activ:
            return einst.get("takt_hms", 25)    
        # 2. Standard-Inaktiv-Takt
        takt = einst.get("takt_akku_inactiv", 120)
        # 3. Nacht-Modus
        if self.app_state.nachtzeit :
            takt = 600
        # 4. Sonderregelungen
        if einst.get("aktuell_aktiv", False):
            takt = self.app_state.takt_48
        if einst.get("hms_bekommt_null", False):
            # Holt den aktuellen Takt von Strom (wird live ausgelesen/berechnet)
            # Falls Strom eine eigene Property hat, könnte hier stehen:self.app_state.strom_instanz.takt
            #takt_strom = 60 if einst.get("aktuell_aktiv", False) else einst.get("takt_akku_inactiv", 120)
            takt = min(120, takt)
        return takt

