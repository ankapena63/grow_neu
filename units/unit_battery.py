import json
import aiohttp
import asyncio
import time
import hashlib
from units.configuration import (
    mache_session
)
from units.calculations import StatusManager, ZeitstempelManager
from units.history import get_history_manager
#from units.unit_dose import dose_tuya
from units.dazu import get_dazu_manager, get_push_manager
from units.state import AppState
import logging

logger = logging.getLogger(__name__)

class GrowattSessionManager:
    def __init__(self, username, password, device_sn, token, *, app_state):
        self.app_state = app_state
        self.username = username
        self.password = self.password_get(password)
        self.device_sn = device_sn
        self.token = token
        self.session = None
        self.logged_in = False
        self.last_noah_data = {}    #tolen meine
        self.akku_login_daten = {}
        self.akku_status_daten = {}
        self.api_lock = asyncio.Lock() # Verhindert parallele API-Abfragen
        self.login_lock = asyncio.Lock()
        self.last_query = 0             # Zeitpunkt der letzten Abfrage
        self.cooldown = 30               # minimale Sekunden zwischen Abfragen

    @property
    def takt(self) -> int:
        if self.app_state.benutzer_activ:
            return self.app_state.einstellungen.get("takt_akku", 61)       
        takt = self.app_state.einstellungen.get("takt_akku_inactiv", 120)
        if self.app_state.nachtzeit and not self.app_state.benutzer_activ:
            takt = self.app_state.einstellungen.get("takt_akku_inactiv", 120)*3
        return takt

    def password_get(self, klar_pass: str) -> str:
        md5_hash = hashlib.md5(klar_pass.encode("utf-8")).hexdigest()
        chars = list(md5_hash)
        for i in range(0, len(chars), 2):
            if chars[i] == '0':
                chars[i] = 'c'
        return  "".join(chars)
        
    async def run_with_lock(self, func, *args, cooldown=0, **kwargs):
      async with self.api_lock:
        now = time.monotonic()
        if cooldown > 0:
            wait = cooldown - (now - self.last_query)
            if wait > 0:
                logger.warning("[Growatt] ❌ Cooldown aktiv → gebe letzte Daten zurück (%.1fs)", wait)
                return self.last_noah_data or {}
        self.last_query = now
        try:
            result = await func(*args, **kwargs)
            return result
        except Exception:
            logger.exception("[Growatt] ❌ Abfragefehler")
            return self.last_noah_data or {}
          
    async def get_noah_queryLastData(self,takt): 
      await self.init_session()
      #url = "https://openapi.growatt.com/v4/new-api/queryLastData"
      httt = self.app_state.zugang.get("url_growatt_alle") 
      url = f"{httt}/queryLastData"
      headers = {
        "token": self.token,
        "Content-Type": "application/x-www-form-urlencoded"
      }
      data = {
        "deviceSn": self.device_sn,
        "deviceType": "noah"
      }  
      try:
       async with self.session.post(url, data=data, headers=headers, timeout=5) as response:
        if response.status == 200:
            data = await response.json()
            if data.get("code") == 0:
                # NOAH-Daten liegen im Array data["noah"][0]
                noah = data.get("data", {}).get("noah", [])
                if not noah:
                    logger.error("Keine NOAH-Daten gefunden")
                    return self.last_noah_data 
                #self.akku_vom_token = noah

                get_history_manager(self.app_state).schreibe_in_roh("akku_token",data)

                obj = noah[0]  # das erste Gerät
                # Werte extrahieren
                laden_entladen = int(obj.get("totalBatteryPackChargingStatus" , 0))
                #if entladen == 2 : =1 
                logger.info("✅Akku Token %s  Sek",takt)
                t1 = float(obj.get("battery1Temp", 0)) 
                t2 = float(obj.get("battery2Temp" , 0))
                self.app_state.temperature = max( t1,t2 ) 
                self.app_state.soc=int(float(obj.get("totalBatteryPackSoc", 0)))
                werte = { 
                        "soc": self.app_state.soc,
                        "soc1": int(float(obj.get("battery1Soc", 0))),
                        "soc2": int(float(obj.get("battery2Soc", 0))),
                        "pac": int(obj.get("pac", 0)) ,
                        "ppv": int(obj.get("ppv", 0)) ,
                        "laden": int(obj.get("totalBatteryPackChargingPower", 0)) ,
                        "laden_entladen": laden_entladen ,
                        "eacTotal": float(obj.get("eacTotal" , 0)),
                        "eacToday": float(obj.get("eacToday" , 0)),
                        "chargeSocLimit": int(obj.get("chargeSocLimit", 99)) ,
                        "dischargeSocLimit": int(obj.get("dischargeSocLimit" , 20)),
                        "battery1Temp" : t1,
                        "battery2Temp" : t2,
                        "battery1SerialNum": obj.get("battery1SerialNum"),
                        "battery2SerialNum": obj.get("battery2SerialNum"),
                        "batteryZahl": int(obj.get("batteryPackageQuantity", 0))  ,
                        "ppv1": round((obj.get("pv1Current") or 0) *(obj.get("pv1Voltage") or 0),0),
                        "ppv2": round((obj.get("pv2Current") or 0) *(obj.get("pv2Voltage") or 0),0),                                                                                                                                                  
                        "batteryCycles": int(obj.get("batteryCycles" , 0)),
                        "daten_von": "Token",
                        "status": int(obj.get("status", -1)) ,
                        "zeit_Noah": obj.get("timeStr"),
                        "takt" : takt,
                        "zeit_meine": ZeitstempelManager.zeitstempel()                
                }
                StatusManager.status_aktualisieren(self.app_state, "akku_token", takt)
                self.last_noah_data = werte
                if (self.app_state.dose_mode == "auto"
                    and not self.app_state.dose_laeuft):
                    manager = getattr(self.app_state, "_dose_manager", None)
                    if manager is None:
                        logger.warning("[Dose in Growatt] Manager ist nicht initialisiert")
                    else:
                        await manager.pruefe(time.monotonic())

                return werte     
            else:
               logger.error("Fehler von Growatt: %s (Code: %s)",
               data.get("message"),
               data.get("code"))          
               return self.last_noah_data
        else:
            logger.error("HTTP-Fehler: %s", response.status)
            return self.last_noah_data
      except Exception:
        logger.exception("Verbindungsfehler")
        logger.error("[Akku] Alle Versuche fehlgeschlagen. Rückfall auf alte Daten.")
        return self.last_noah_data 
    #########################
    # SOC-Limit setzen
    #########################
    async def set_limit_soc(self, was, soc_soll, soc_ist, min_v, max_v):
      if soc_soll == soc_ist:
        return {
            "result": 0,
            "title": f"GROWATT set SOC Limit {was}",
            "message": f"{was.capitalize()} SOC Limit bereits korrekt ({soc_soll}%)"
        }
      if soc_soll < min_v or soc_soll > max_v:
        return {
            "result": -1,
            "title": f"GROWATT set SOC Limit {was}",
            "message": f"Ungültiger Wert für {was}-SOC: {soc_soll} ❌"
        }

      url_ende = "setLowLimitSoc" if was == "min" else "setHighLimitSoc"

      httt = self.app_state.zugang.get("url_growatt_alle")
      url = f"{httt}/{url_ende}"

      headers = {
        "token": self.token, #state.zugang.get("token"),
        "Content-Type": "application/x-www-form-urlencoded"
    }
      payload = {
        "deviceSn": self.device_sn,  #state.zugang.get("deviceSn"),
        "deviceType": "noah",
        "value": int(soc_soll)
    }
      try:
        await self.init_session()

        async with self.session.post(
            url,
            data=payload,
            headers=headers,
            timeout=5
        ) as response:
            if response.status != 200:
                return {
                    "result": -1,
                    "title": f"GROWATT set SOC Limit {was}",
                    "message": f"HTTP-Fehler ❌ ({response.status})"
                }
            resp = await response.json()
            if resp.get("code") == 0:
                logger.info("%s SOC Limit erfolgreich gesetzt ✅ (%s%%)",was.capitalize(), soc_soll)
                return {
                    "result": 0,
                    "title": f"GROWATT set SOC Limit {was}",
                    "message": (
                        f"{was.capitalize()} SOC Limit erfolgreich gesetzt ✅ "
                        f"({soc_soll}%)"
                    )
                }
            return {
                "result": -1,
                "title": f"GROWATT set SOC Limit {was}",
                "message": str(
                    resp.get("message")
                    or f"Fehler beim Setzen des {was}-SOC Limits ❌"
                )
            }
      except Exception as e:
        logger.exception("[Growatt] Fehler beim Setzen des %s-SOC-Limits", was)
        return {
            "result": -1,
            "title": f"GROWATT set SOC Limit {was}",
            "message": str(e)
        }
    
    async def init_session(self):
        self.session = await mache_session(self.app_state, "session_growatt", timeout=10)

    async def login(self):
        await self.init_session()
        #url = "https://openapi.growatt.com/newTwoLoginAPI.do"
        url = self.app_state.zugang.get("url_login") 
        data = {
            "userName": self.username,
            "password": self.password,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            async with self.session.post(url, data=data, headers=headers, timeout=5) as response:
                text = await response.text()
                if response.status == 200 and "plantId" in text:
                    self.logged_in = True
                    get_history_manager(self.app_state).schreibe_in_roh("akku_status",json.loads(text))
                    logger.info("✅Growatt Login")
                else:
                    self.logged_in = False
                    logger.error("[Growatt] ❌ Login fehlgeschlagen: %s ",text)
        except Exception:
            self.logged_in = False
            logger.exception("[Growatt] ⚠️ Fehler beim Login")

    async def get_status(self,takt):      
        await self.ensure_login()

        #url = "https://openapi.growatt.com/noahDeviceApi/noah/getSystemStatus"
        url = self.app_state.zugang.get("url_status") 
        data = {"deviceSn": self.device_sn}
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            async with self.session.post(url, data=data, headers=headers, timeout=5) as response:
                if response.content_type != "application/json":
                    logger.error("[Growatt] ❌ Ungültiger Content-Type, evtl. ausgeloggt")
                    self.logged_in = False
                    return {}
                result = await response.json()
                get_history_manager(self.app_state).schreibe_in_roh("akku_login",result)
                
                if "obj" not in result:
                    logger.error("[Growatt] ❌ Antwort ohne 'obj' %s", result)
                    return {}
                obj = result.get("obj", {})
                logger.info("✅Growatt Daten %s Sek",takt)
                #  document.getElementById("aknku-ppv").textContent = d.akku.ppv;
                self.app_state.soc = int(float(obj.get("soc", 0)))
                res ={ 
                        "soc": self.app_state.soc,
                        "pac": int(obj.get("pac" , 0)),
                        "ppv": int(obj.get("ppv", 0)) ,
                        "laden": int(obj.get("chargePower" , 0)) - int(obj.get("disChargePower" , 0)),
                        "eacTotal": float(obj.get("eacTotal" ,0)),
                        "eacToday": float(obj.get("eacToday", 0)) ,
                        "daten_von": "Growatt",
                        "status": int(obj.get("status" , -1)),
                        "takt" : takt,
                        "zeit_meine": ZeitstempelManager.zeitstempel()
                } 
                StatusManager.status_aktualisieren(self.app_state, "akku_login", takt)
                self.akku_status_daten = res
                return res
        except Exception:
            logger.exception("Akku Login fehlgeschlagen")
            self.logged_in = False
            #Beim nächsten Aufruf wird automatisch eine frische Session erstellt.
            if self.session and not self.session.closed:
                await self.session.close()
            self.session = None
            return self.last_noah_data 

    async def ensure_login(self):
        await self.init_session()
        if self.logged_in:
            return
        async with self.login_lock:
             if not self.logged_in:
                await self.login()           

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("[Growatt] Session geschlossen")
       # url = f"http://192.168.1.100:8087/getPlainValue/{datapoint}"
       # url = "http://192.168.1.100:8087/getPlainValue/growatt.0.10033400.devices.0PVP50ZR16MT005C.historyLast.pac"

    async def get_iobroker_datapoint(self, datapoint):
        await self.init_session()  # Session sicherstellen
        #url = f"http://192.168.178.57:8087/getPlainValue/{datapoint}"
        url = f"{self.app_state.zugang.get('ip_haupt')}{self.app_state.zugang.get('ip_iobroker')}:8087/getPlainValue/{datapoint}"
        try:
            async with self.session.get(url, timeout=10) as response:
                if response.status == 200:
                    text = await response.text()
                    value = float(text.strip())
                    return value
                else:
                    logger.error("[ioBroker] ❌ HTTP-Fehler %s für %s",response.status,datapoint)
                    return 0.0
        except asyncio.TimeoutError:
             logger.error("[ioBroker] ⏱️ Timeout bei URL: %s",url)
        except asyncio.CancelledError:
             logger.error("[ioBroker] ❌ Verbindung abgebrochen (CancelledError) bei URL: %s",url)
        except aiohttp.ClientError as e:
             logger.error("[ioBroker] ⚠️ HTTP-Fehler bei URL %s: %s", url, e)     
        except Exception:
             logger.exception("[ioBroker] ❗ Unerwarteter Fehler bei %s", datapoint)
        return 0.0  # Rückgabe im Fehlerfall

    async def get_iobroker(self):
        #print("[ioBroker] 📥 Datenabfrage gestartet (parallel) ...")
        datapoints = {
        "soc": "growatt.0.10033400.devices.0PVP50ZR16MT005C.historyLast.battery1Soc",
        "pac": "growatt.0.10033400.devices.0PVP50ZR16MT005C.historyLast.pac",
        "ppv": "growatt.0.10033400.devices.0PVP50ZR16MT005C.historyLast.ppv",
        "laden": "growatt.0.10033400.devices.0PVP50ZR16MT005C.historyLast.totalBatteryPackChargingPower",
        "eacTotal": "growatt.0.10033400.devices.0PVP50ZR16MT005C.historyLast.eacTotal",
        "eacToday": "growatt.0.10033400.devices.0PVP50ZR16MT005C.historyLast.eacToday"
       }
    # Alle Abfragen gleichzeitig starten
        results = await asyncio.gather(
            *[self.get_iobroker_datapoint(dp) for dp in datapoints.values()],
             return_exceptions=True
        )
    # Ergebnisse korrekt zuordnen
        daten = {key: (val if not isinstance(val, Exception) else 0.0)
             for key, val in zip(datapoints.keys(), results)}
        daten["daten_von"] = "IoBroker"
        return daten

    async def akku_daten(
        self,
        alt_daten: dict,
        takt: int = 60,
        ) -> dict:
      try:
        if self.app_state.einstellungen.get("abfrage_growatt", False):
            status2, status1 = await asyncio.gather(
                self.app_state.growatt.get_status(takt),
                self.app_state.growatt.run_with_lock(
                    self.app_state.growatt.get_noah_queryLastData,
                    takt,
                    cooldown=60,
                ),
            )
            if not status1:
                status1 = alt_daten or {}
            if status2:
                status = {**status1, **status2}
            else:
                status = status1
        else:
            status = await self.app_state.growatt.get_iobroker() or {}
            status["zeit_meine"] = ZeitstempelManager.zeitstempel()

        temp1 = status.get("battery1Temp", 0)
        temp2 = status.get("battery2Temp", 0)
        if temp1 > 44 or temp2 > 44:
            max_temp = max(temp1, temp2)
            message = (f"⚠️ Akku zu heiß: {max_temp}°C! Bitte für Kühlung/Schatten sorgen.")
            await get_push_manager(self.app_state).sende_push(message, 600, 5)
        status_akku = status.get("status", 1)
        if status_akku != 1:
            await get_push_manager(self.app_state).sende_push(f"Akku status: {status_akku}", 3600, 4)
        return status
      except Exception as error:
        logger.exception("[Growatt] Fehler")
        alt_daten = alt_daten or {}
        alt_daten["fehler"] = str(error)
        alt_daten["zeit_fehler"] = ZeitstempelManager.zeitstempel()
        return alt_daten

    async def pruefe( self, zeit: float) -> None:
      takt = self.takt
      StatusManager.status_aktualisieren(self.app_state, "akku_token", takt,False)
      StatusManager.status_aktualisieren(self.app_state, "akku_login", takt,False)

      if zeit - self.app_state.start_akku <= takt and not self.app_state.erste_abfrage:
        return
      
      solax_l_mittelwert_nutzen = self.app_state.einstellungen.get( "solax_l_mittelwert_nutzen",False, )
      logger.info("🔋Akkus %s Sek", takt)
      self.app_state.alle_daten["akku"] = await self.akku_daten(
        self.app_state.alle_daten.get("akku", {}), takt)
      if solax_l_mittelwert_nutzen and not self.app_state.nachtzeit:
        self.app_state.solax_local = ( await self.app_state.solax.abfrage_local(takt))
        self.app_state.start_solax_l = zeit
      self.app_state.start_akku = zeit
      await get_dazu_manager(self.app_state).rechne_dazu()
    
