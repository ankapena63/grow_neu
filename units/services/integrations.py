"""Integrations services."""
import aiohttp
import asyncio
import json
import time
import logging
logger = logging.getLogger(__name__)
from .calculations import haus_verbrauch_get, mittelwert_get, status_aktualisieren, zeitstempel
from .configuration import mache_session
from .history import schreibe_in_roh, speichere_aktuell_wert

async def abfrage_tasmota(app_state, alt_daten: dict,takt: int = 5) -> dict:
    #url = "http://192.168.178.29/cm?cmnd=status%2010"  
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
                schreibe_in_roh(app_state, "tasmota",json_data)
                # Zugriff auf die Werte
                StatusSNS = json_data.get("StatusSNS", {})
                sm = json_data.get("StatusSNS", {}).get("SM", {})
                # Falls der Key "SM" gar nicht existiert, vorsichtshalber leeres dict
                if not sm:
                    logger.error(f"[Tasmota] Warnung: keine daten 'SM' Datenpfad nicht gefunden")
                
                hms0 =StatusSNS.get("hms0", 1)
                await vergleich_hms0(app_state, hms0)

                json_dat = {
                    "Gesamt": sm.get("Gesamt", 0.0),
                    "Einspeise": sm.get("Einspeise", 0.0),
                    "Actuel": sm.get("Actuel", 0.0),
                    "V1": sm.get("V1", 0.0),
                    "V2": sm.get("V2", 0.0),
                    "V3": sm.get("V3", 0.0),
                    "vdazu": StatusSNS.get("vdazu", 0),
                    #"hms0": hms0,
                    "takt" : takt,
                    "zeit_meine": zeitstempel()
                }
                
                status_aktualisieren(app_state, "strom", takt)
                logger.info("Tasmota Aufruf✅ %s Sek",takt)
                logger.debug("Daten %s",json_dat)
                return json_dat
    except asyncio.TimeoutError:
        fehler = "Timeout"
        logger.warning("[Tasmota] Timeout")
    except aiohttp.ClientError as ex:
        fehler = str(ex)
        logger.warning("[Tasmota] HTTP-Fehler: %s", ex)
    except Exception:
        logger.exception("[Tasmota] Unerwarteter Fehler")
        fehler = "Unbekannter Fehler"
    res = (alt_daten or {}).copy()
    res.update({
             "fehler": fehler or "Unbekannter Fehler",
            "zeit_fehler": zeitstempel()
        })
    return res

async def abfrage_solax(app_state, alt_daten: dict, takt: int,  versuche=2, wartezeit=5):  
    session = await mache_session(app_state, "session_solax_c") 
    #url = "https://www.solaxcloud.com/proxyApp/proxy/api/getRealtimeInfo.do"
    #    params = {"tokenId": "202306170351297281979113","sn": "SXZJYAUMNM"}
    url = app_state.zugang.get("solax_c_url")
    params = {
        "tokenId" : app_state.zugang.get("solax_c_tokenId"),
        "sn"      : app_state.zugang.get("solax_c_sn")
    }
    for versuch in range(versuche):
        try:      
                #async with session.get(url, timeout=5) as response: 
                async with session.get(url, params=params, timeout=10) as response:
                    response.raise_for_status()
                    result = await response.json()
                    if result.get("success") and "result" in result:
                        schreibe_in_roh(app_state, "solax_c",result)
                        r = result["result"]
                        res= {
                                "heute": float(r.get("yieldtoday", 0.0)),
                                "gesamt": float(r.get("yieldtotal", 0.0)),
                                "acpower": float(r.get("acpower", 0.0)),
                                "feedinpower": float(r.get("feedinpower", 0.0)),
                                "dc1": float(r.get("powerdc1", 0.0)),
                                "dc2": float(r.get("powerdc2") or 0.0),
                                "inverterStatus": r.get("inverterStatus", "unbekannt"),
                                "upload_zeit" :  r.get("uploadTime"),
                                "takt" : takt,
                                "zeit_meine": zeitstempel()
                        }
                        status_aktualisieren(app_state, "solax_c", takt)
                        return res
                    else:
                        logger.error(f"[Solax] Ungültige Antwort erhalten (Versuch {versuch + 1}).")
        except Exception:
            logger.warning("[Solax] Fehler Versuch %s",versuch+1)
            await asyncio.sleep(wartezeit)
    alt_daten = alt_daten or {}
    alt_daten["fehler"] = "Solax API nicht erreichbar"
    alt_daten["zeit_fehler"] = zeitstempel()
    logger.error("[Solax C] Alle Versuche fehlgeschlagen. Rückfall auf alt_daten.")
    return alt_daten

async def abfrage_solax_local(app_state, takt: int, versuche: int = 2, basis_wartezeit: int = 2) -> dict:
    session = await mache_session(app_state, "session_solax_l") 
    #url = "http://192.168.178.92"
    url  =  app_state.zugang.get("solax_l_url")
    #payload = "optType=ReadRealTimeData&pwd=SXZJYAUMNM"
    payload = f"optType=ReadRealTimeData&pwd={app_state.zugang.get('solax_c_sn')}"
    headers = {"Content-Type": "application/x-www-form-urlencoded"} 
    for versuch in range(versuche):
            try:       
                async with session.post(url, data=payload, headers=headers, timeout=5) as response:
                    text = await response.text()
                    if response.status == 200:
                        daten = text.split(",")
                        if len(daten) < 17:
                            logger.error(f"[Solax Lokal] Daten unvollständig (Länge {len(daten)})")
                            continue # Nächster Versuch
                        schreibe_in_roh(app_state, "solax_l",json.loads(text))
                        logger.info("Solax L✅ %s Sek V:%s",takt,versuch + 1)
                        aktuell = int(daten[5]) if len(daten) > 5 else -1
                        app_state.solax_l_mittelwert = int(
                            round(mittelwert_get(aktuell, app_state.solax_l_werte), 0)
                        )
                        res = {
                            "sn": daten[0][7:17] if len(daten) > 0 and len(daten[0]) >= 17 else "?",
                            "aktuell": aktuell,
                            "gesamt": float(daten[14]) / 10 if len(daten) > 14 else -1,
                            "heute": float(daten[16]) / 10 if len(daten) > 16 else -1,
                            "takt" : takt,                           
                            "zeit_meine": zeitstempel()
                        }
                        if app_state.einstellungen.get("aktuell_aktiv", True):
                            speichere_aktuell_wert(app_state, "solax",aktuell)
                        
                        status_aktualisieren(app_state, "solax_l", takt)
                        app_state.solax_local =res
                        return res
                    else:
                        logger.error(f"[Solax Lokal] HTTP {response.status} bei Versuch {versuch + 1}")
            except Exception:
                logger.exception("[Solax Lokal] Fehler Versuch %s",versuch + 1)
                await asyncio.sleep(basis_wartezeit * (2 ** versuch))
    logger.error("[Solax Lokal] Alle Versuche fehlgeschlagen. Fallback.")
    app_state.solax_l_mittelwert = 0
    res = app_state.solax_local.copy() if app_state.solax_local else {}
    res["fehler"] = f"Lokale Solax-API nicht erreichbar ({url})"
    res["zeit_fehler"] = zeitstempel()
    return res

async def abfrage_hms(
        app_state,
        alt_daten: dict, 
        takt: int,
        versuche: int = 3, 
        basis_wartezeit: int = 2
) -> dict:
    #url = "http://192.168.178.44/api/livedata/status/inverters"
    #auth = aiohttp.BasicAuth("admin", "nuttertools")
    url = f"{app_state.zugang.get('ip_haupt')}{app_state.zugang.get('ip_hms')}/api/livedata/status/inverters"
    auth = aiohttp.BasicAuth(app_state.zugang.get("hms_name"), app_state.zugang.get("hms_pas"))
    session = await mache_session(app_state, "session_hms", auth=auth)
    for versuch in range(versuche):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                response.raise_for_status()
                daten = await response.json()
                schreibe_in_roh(app_state, "hms",daten)
                total = daten.get("total", {})
                # Sicherer Zugriff auf die Inverter-Liste
                inverters = daten.get("inverters", [])
                inverter = inverters[0] if inverters else {}
                
                limit = inverter.get("limit_absolute", 0) 
                # Achtung: Prüfen ob limit_relative existiert
                # limit = inverter.get("limit_relative", 0) * 8 
                # pruefe_hms_limit(limit,nullen)   in schleife

                res ={
                    "heute": total.get("YieldDay", {}).get("v", 0),
                    "gesamt": total.get("YieldTotal", {}).get("v", 0),
                    "aktuell": total.get("Power", {}).get("v", 0),
                    "limit": limit,
                    "producing": inverter.get("producing", False),
                    "reachable": inverter.get("reachable", False),
                    "takt" : takt,
                    "serial":inverter.get("serial", ""),
                    "zeit_meine": zeitstempel()
                }

                status_aktualisieren(app_state, "hms", takt)
                return res
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("[HMS] Verbindungsproblem Versuch %s: %s",versuch + 1, e)
        except Exception :
            logger.exception("[HMS] Unerwarteter Fehler:")
            break # Bei Logikfehlern macht ein Retry oft keinen Sinn
        
        if versuch < versuche - 1:
            await asyncio.sleep(basis_wartezeit * (2 ** versuch))
    # Fallback
    res = (alt_daten or {}).copy()
    res.update({"fehler": "HMS API nicht erreichbar", 
                "zeit_fehler": zeitstempel()})
    logger.error(f"[HMS] Alle Versuche fehlgeschlagen. ")
    return res

async def setze_hms_limit(app_state, limit_watt: int) -> bool:
    try:
        limit_watt = int(limit_watt)
        dtu_ip = (
            f"{app_state.zugang.get('ip_haupt')}"
            f"{app_state.zugang.get('ip_hms')}"
        )
        serial = (app_state.alle_daten.get("hms", {}).get("serial", ""))
        if not serial:
            logger.warning("[HMS] Keine Seriennummer für OpenDTU vorhanden.")
            return False
        url = f"{dtu_ip}/api/limit/config"
        payload = {
            "serial": serial,
            "limit_type": 0,
            "limit_value": limit_watt
        }
        # dieselbe HMS-Session wie bei abfrage_hms()
        session = await mache_session(
            app_state,
            "session_hms",
            auth=aiohttp.BasicAuth(
                app_state.zugang.get("hms_name"),
                app_state.zugang.get("hms_pas")
            )
        )
        async with session.post(
            url,
            data={"data": json.dumps(payload)},
            timeout=aiohttp.ClientTimeout(total=5)
        ) as response:
            response.raise_for_status()
            ergebnis = await response.json()
            if ergebnis.get("type") == "success":
               logger.info("[HMS] OpenDTU Limit %s W gesendet: %s",limit_watt,ergebnis)
                # WICHTIG: sofort lokalen Wert aktualisieren
               app_state.alle_daten.setdefault("hms", {})["limit"] = limit_watt
               return True
            logger.warning("[HMS] Limit nicht übernommen: %s", ergebnis)
            return False
    except Exception:
        logger.exception("[HMS] Fehler beim Setzen des Limits")
        return False

async def abfrage_strom(app_state, alt_daten: dict, 
                        ip_smart: str = "123",
                        takt: int=4,
                        versuche: int = 3, basis_wartezeit: int = 2) -> dict:
    session = await mache_session(app_state, "session_strom")
    url = f"{app_state.zugang.get('ip_haupt')}{ip_smart}/smartdaten"
    for versuch in range(versuche):
        try:
            async with session.get(url, timeout=5) as response: 
                response.raise_for_status()
                daten = await response.json()
                # Daten vervollständigen
                daten["takt"] = takt
                daten["zeit_meine"] = zeitstempel()
                status_aktualisieren(app_state, "strom", takt)
                logger.info(f"[Strom] OK bei Versuch {versuch + 1}")
                return daten
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
             logger.warning("[Strom] Verbindungsproblem Versuch %s: %s",versuch + 1,e )
        except Exception:
            logger.exception("[Strom] Unerwarteter Fehler: ")
            break # Bei echten Programmierfehlern (z.B. JSON-Parsing) kein Retry
        if versuch < versuche - 1:
            await asyncio.sleep(basis_wartezeit * (2 ** versuch))
    # Alle Versuche fehlgeschlagen → Fallback
    res = (alt_daten or {}).copy()
    res.update({
        "fehler": f"Strom API {url} nicht erreichbar",
        "zeit_fehler": zeitstempel()
    })
    logger.error("[Strom] Alle Versuche fehlgeschlagen. Rückfall auf alt_daten.")
    return res

async def sende_vdazu_tasmota(app_state, vdazu_wert: int, timeout_sek: int = 5) -> dict:
    """
    Sendet einen Wert an den Tasmota und erwartet eine HTML-Antwort.
    ;senden http://192.168.178.119/cm?cmnd=script+%3Evdazu=224;time=600
    """
    session = await mache_session(app_state, "session_strom")
    lan_ip = app_state.zugang["ip_tasmota"]
    soc   = app_state.soc
    ppv   = app_state.alle_daten.get("akku", {}).get("ppv", 0) or 0
    hms   = app_state.alle_daten.get("hms", {}).get("aktuell", 0) or 0
    solax = app_state.alle_daten.get("solax", {}).get("acpower", 0) or 0
    haus = haus_verbrauch_get(app_state)
    nullen = app_state.einstellungen.get("hms_bekommt_null",False)
    hms0   = 0 if nullen else 1   
  
  
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
    #url = f"http://192.168.178.{lan_ip}/cm?cmnd=script+%3Etime=600;vdazu={str(vdazu_wert)};solax={str(solax)};soc={str(soc)};hms={str(hms)}"
    try:       
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout_sek)) as response:
                response.raise_for_status()
                html = await response.text()
                logger.debug("Tasmota Send-Antwort: %s", html)
                logger.info("Tasmota senden ✅ " )#%s",html
                return {
                    "status": "OK", 
                    "ip": lan_ip, 
                    "wert": vdazu_wert, 
                    "html": html
                }           

    except asyncio.TimeoutError:
        logger.warning("[Tasmota] Timeout beim Senden an %s", url)
        return {"error": f"Timeout beim Senden an {url}"}
    except aiohttp.ClientError as e:
        logger.error("[Tasmota] HTTP-Fehler: %s", e)
        return {"error": f"HTTP-Fehler: {e}"}
    except Exception:
        logger.exception("[Tasmota] Allgemeiner Fehler")
        return {"error": "Allgemeiner Fehler"}

async def sende_vdazu_smart(app_state, vdazu_wert: int, timeout_sek: int = 5) -> dict:
    """
    Sendet einen Wert an den ESP32 und erwartet eine HTML-Antwort.
    """
    session = await mache_session(app_state, "session_strom")
    lan_ip = app_state.zugang["ip_smart"]
    #url = f"http://192.168.178.{lan_ip}/send_dazu?vdazu={str(vdazu_wert)}"
    url = f"{app_state.zugang.get('ip_haupt')}{lan_ip}/send_dazu?vdazu={vdazu_wert}"
    try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout_sek)) as response:
                response.raise_for_status()
                html = await response.text()
                return {
                    "status": "OK", 
                    "ip": lan_ip, 
                    "wert": vdazu_wert, 
                    "html": html
                }
    except asyncio.TimeoutError:
        logger.warning("[Smart] Timeout beim Senden an %s", url)
        return {"error": f"Timeout beim Senden an {url}"}
    except aiohttp.ClientError as e:
        logger.error("[Smart] HTTP-Fehler: %s", e)
        return {"error": f"HTTP-Fehler: {e}"}
    except Exception:
        logger.exception("[Smart] Allgemeiner Fehler")
        return {"error": "Allgemeiner Fehler"}

async def sende_push(app_state, nachricht, pause=3600, prio=3):
    if not app_state.einstellungen.get("nachricht_app", False):
        return
    jetzt = time.time()  
    # Sicherstellen, dass das Dictionary existiert (verhindert Fehler)
    if not hasattr(app_state, 'letzte_push_zeiten'):
        app_state.letzte_push_zeiten = {}
    # Check für diese spezifische Prio
    letzte_zeit = app_state.letzte_push_zeiten.get(prio, 0)
    if jetzt - letzte_zeit < pause:
        return
    session = await mache_session(app_state, "session_push") 
    # WICHTIG: Keine Umlaute in den Header-Werten (verursacht oft 400)
    headers = {
        "Priority": str(prio),
        "Title": "Solar-Monitor", 
        "Tags": "warning" if prio >= 4 else "info"
    }
    topic = "SolaxHmsGrowattvvv"
    url = f"https://ntfy.sh/{topic}"
    try:
        async with session.post(url, data=nachricht.encode('utf-8'), headers=headers) as resp:
            if resp.status == 200:
                logger.info("✅ Push Prio: %s gesendet",prio)
                app_state.letzte_push_zeiten[prio] = jetzt
            else:
                error_text = await resp.text()
                logger.error("❌ ntfy Fehler %s : %s",resp.status,error_text)
    except Exception:
        logger.exception("❌ Push-Verbindung fehlgeschlagen")

async def vergleich_hms0(app_state, hms0): 
    nullung = app_state.einstellungen.get("hms_bekommt_null", False)
    if (nullung and hms0 ==0 ) or (not nullung and hms0 ==1):
       return    
    await sende_vdazu_tasmota(app_state, 0)  
    logger.info("An Tasmota senden %s= %s",nullung,hms0)
