"""HTTP clients for Solax cloud and local APIs."""
import asyncio
import json
import logging
import aiohttp
from aiohttp import ClientTimeout
from units.calculations import MittelwertManager, StatusManager, ZeitstempelManager
from units.configuration import mache_session
from units.history import get_history_manager
from units.state import AppState

logger = logging.getLogger(__name__)

class Solax:
    
    def __init__(self, app_state: AppState):
        self.app_state = app_state

    async def abfrage_cloud(
        self,
        alt_daten: dict,
        takt: int,
        versuche: int = 2,
        wartezeit: int = 5,
    ):
        app_state = self.app_state
        session = await mache_session(app_state, "session_solax_c")
        url = app_state.zugang.get("solax_c_url")
        params = {
            "tokenId": app_state.zugang.get("solax_c_tokenId"),
            "sn": app_state.zugang.get("solax_c_sn"),
        }
        for versuch in range(versuche):
            try:
                async with session.get(
                    url,
                    params=params,
                    timeout=ClientTimeout(total=10),
                ) as response:
                    response.raise_for_status()
                    result = await response.json()

                    if result.get("success") and "result" in result:
                        get_history_manager(app_state).schreibe_in_roh("solax_c", result)
                        data = result["result"]
                        normalized = {
                            "heute": float(data.get("yieldtoday", 0.0)),
                            "gesamt": float(data.get("yieldtotal", 0.0)),
                            "acpower": float(data.get("acpower", 0.0)),
                            "feedinpower": float(data.get("feedinpower", 0.0)),
                            "dc1": float(data.get("powerdc1", 0.0)),
                            "dc2": float(data.get("powerdc2") or 0.0),
                            "inverterStatus": data.get(
                                "inverterStatus",
                                "unbekannt",
                            ),
                            "upload_zeit": data.get("uploadTime"),
                            "takt": takt,
                            "zeit_meine": ZeitstempelManager.zeitstempel(),
                        }
                        StatusManager.status_aktualisieren(app_state, "solax_c", takt)
                        return normalized

                    logger.error(
                        "[Solax] Ungültige Antwort erhalten (Versuch %s).",
                        versuch + 1,
                    )

            except Exception:
                logger.warning(
                    "[Solax] Fehler bei Cloud-Abfrage, Versuch %s/%s",
                    versuch + 1,
                    versuche,
                    exc_info=True,
                )

            # Nur zwischen fehlgeschlagenen Versuchen warten.
            if versuch < versuche - 1:
                await asyncio.sleep(wartezeit)

        alt_daten = alt_daten or {}
        alt_daten["fehler"] = "Solax API nicht erreichbar"
        alt_daten["zeit_fehler"] = ZeitstempelManager.zeitstempel()
        logger.error(
            "[Solax C] Alle Versuche fehlgeschlagen. Rückfall auf alt_daten."
        )
        return alt_daten

    async def abfrage_local(
        self,
        takt: int,
        versuche: int = 2,
        basis_wartezeit: int = 2,
    ) -> dict:
        app_state = self.app_state
        session = await mache_session(app_state, "session_solax_l")
        url = app_state.zugang.get("solax_l_url")
        payload = "optType=ReadRealTimeData&pwd=" + str(app_state.zugang.get("solax_c_sn", ""))
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        for versuch in range(versuche):
            try:
                async with session.post(
                    url,
                    data=payload,
                    headers=headers,
                    timeout=5,
                ) as response:
                    text = await response.text()
                    if response.status == 200:
                        data = text.split(",")
                        if len(data) < 17:
                            logger.error("[Solax Local] Daten unvollständig (Länge %s)",len(data))
                            continue
                        schreibe_in_roh( app_state,"solax_l",json.loads(text) )
                        logger.info("Solax L✅ %s Sek V:%s", takt, versuch + 1)
                        aktuell = int(data[5]) if len(data) > 5 else -1
                        app_state.solax_l_mittelwert = int( round(MittelwertManager.mittelwert_get( aktuell, app_state.solax_l_werte,  ), 0, ))
                        result = {
                            "sn": ( data[0][7:17] if len(data) > 0 and len(data[0]) >= 17  else "?" ),
                            "aktuell": aktuell,
                            "gesamt": (float(data[14]) / 10 if len(data) > 14  else -1),
                            "heute": ( float(data[16]) / 10    if len(data) > 16  else -1),
                            "takt": takt,
                            "zeit_meine": ZeitstempelManager.zeitstempel(),
                        }
                        if app_state.einstellungen.get("aktuell_aktiv", True):
                            get_history_manager(app_state).speichere_aktuell_wert("solax", aktuell, )
                        StatusManager.status_aktualisieren(app_state, "solax_l", takt)
                        app_state.solax_local = result
                        return result
                    logger.error("[Solax Local] HTTP %s bei Versuch %s",response.status,versuch + 1,  )
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                logger.warning("[Solax Local] Verbindungsfehler Versuch %s: %s",versuch + 1,error)
                if versuch < versuche - 1:
                    await asyncio.sleep(basis_wartezeit * (2 ** versuch))
            except Exception:
                logger.exception("[Solax Local] Fehler Versuch %s", versuch + 1)
                if versuch < versuche - 1:
                    await asyncio.sleep(basis_wartezeit * (2 ** versuch))

        logger.error("[Solax Local] Alle Versuche fehlgeschlagen. Fallback.")
        #app_state.solax_l_mittelwert = 0
        result = app_state.solax_local.copy() if app_state.solax_local else {}
        result["fehler"] = f"Locale Solax-API nicht erreichbar ({url})"
        result["zeit_fehler"] = ZeitstempelManager.zeitstempel()
        return result

    async def pruefe_local(self, zeit: float) -> None:
        app_state = self.app_state
        takt = self.takt_local
        StatusManager.status_aktualisieren(app_state, "solax_l", takt,False)
        if ( zeit - app_state.start_solax_l > takt
            or app_state.erste_abfrage
        ):
            if app_state.alle_daten.get("solax", {}).get("acpower", 0) != 0:
                app_state.solax_local = await self.abfrage_local(takt)
                app_state.start_solax_l = zeit
        if zeit - app_state.start_solax_l > takt * 10:
            app_state.solax_local["fehler"] = (
                "Locale Solax-API zu lang nicht erreichbar"
            )
            app_state.solax_local["zeit_fehler"] = ZeitstempelManager.zeitstempel()

    async def pruefe_cloud(self, zeit: float) -> None:
        app_state = self.app_state
        takt = self.takt_cloud
        StatusManager.status_aktualisieren(app_state, "solax_c", takt,False)
        if zeit - app_state.start_solax_c > takt or app_state.erste_abfrage:
            logger.info("☁️ Solax C✅ %s Sek", takt)
            app_state.alle_daten["solax"] = await self.abfrage_cloud(
                app_state.alle_daten.get("solax", {}),
                takt
            )
            app_state.start_solax_c = zeit
   
    async def pruefe(self, zeit: float) -> None:
        await self.pruefe_cloud(zeit)
        await self.pruefe_local(zeit)
   
    @property
    def takt_cloud(self) -> int:
        einst = self.app_state.einstellungen
        if self.app_state.benutzer_activ:
            return einst.get("takt_solax_c",300)
        else:
            return einst.get("takt_cloud_nacht",600)
            
    @property
    def takt_local(self) -> int:
        einst = self.app_state.einstellungen
        if self.app_state.benutzer_activ:
            return einst.get("takt_solax_l", 25)   
        if einst.get("aktuell_aktiv", False):
             return self.app_state.takt_48
        takt = einst.get("takt_akku_inactiv", 120)
        if self.app_state.nachtzeit :
            takt = einst.get("takt_cloud_nacht",600)*3
        return takt

