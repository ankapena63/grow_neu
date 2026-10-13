from .config import DATA_DIR
import aiohttp
import csv
import json
import subprocess
import logging
logger = logging.getLogger(__name__)
INIT_FILE   = DATA_DIR / "init.json"
INIT_ZUGANG = DATA_DIR / "init_zugang.json"

class SessionManager:
    """Kapselt die Erstellung und Wiederverwendung von aiohttp-Sessions."""

    def __init__(self, app_state):
        self.app_state = app_state

    @classmethod
    def fuer(cls, app_state):
        """Liefert den gemeinsamen SessionManager dieses AppState."""
        manager = getattr(app_state, "_session_manager", None)
        if manager is None:
            manager = cls(app_state)
            app_state._session_manager = manager
        return manager

    async def erstelle(self, name, *, auth=None, headers=None, timeout=10):
        """
        Gibt die benannte Session zurück oder erstellt sie bei Bedarf neu.
        """
        app_state = self.app_state
        session = getattr(app_state, name, None)
        if session is None or session.closed:
            connector = aiohttp.TCPConnector(
                limit=20,
                keepalive_timeout=60,
                limit_per_host=10,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            session = aiohttp.ClientSession(
                connector=connector,
                auth=auth,
                headers=headers,
                timeout=aiohttp.ClientTimeout(
                    total=timeout,
                    connect=5,
                    sock_connect=5,
                    sock_read=5,
                ),
            )
            setattr(app_state, name, session)
            logger.info("Neue Session erstellt: %s", name)
        return session



class TagesdatenManager:
    """Kapselt das Einlesen der gespeicherten Tageswerte."""

    @staticmethod
    def laden(name="tageswerte0.csv"):
        dateiname = DATA_DIR / name
        try:
            with dateiname.open(newline="", encoding="utf-8") as csvfile:
                reader = csv.reader(csvfile)
                next(reader, None)
                daten = []
                for row in reader:
                    if len(row) >= 6:
                        try:
                            neue_reihenfolge = [
                                row[0],
                                f"{float(row[1]):.2f}",
                                f"{float(row[2]):.2f}",
                                f"{float(row[3]):.2f}",
                                f"{float(row[4]):.2f}",
                                f"{float(row[5]):.2f}",
                            ]
                            daten.append(neue_reihenfolge)
                        except ValueError:
                            logger.exception(
                                "Fehler beim Verarbeiten der Zeile: %s", row
                            )
        except FileNotFoundError:
            logger.error("DATEI NICHT GEFUNDEN!")
            return []
        daten.reverse()
        return daten


class EinstellungenManager:
    """Kapselt Laden und Speichern von Einstellungen und Zugangsdaten."""

    @staticmethod
    async def speichere_einstellungen(app_state, daten):
        async with app_state.save_lock:
            INIT_FILE.parent.mkdir(parents=True, exist_ok=True)
            try:
                with INIT_FILE.open("w", encoding="utf-8") as f:
                    json.dump(daten, f, indent=4, ensure_ascii=False)
                logger.info("Einstellungen gespeichert.")
            except Exception:
                logger.exception("Speicherfehler:")
    
    @staticmethod
    def lade_einstellungen(alte_einstellungen):
        """Lädt die Einstellungen aus INIT_FILE. Bei Fehlern bleiben die alten Einstellungen erhalten."""
        try:
            with INIT_FILE.open("r", encoding="utf-8") as f:
                logger.info(f"Einstellungen erfolgreich von  {INIT_FILE} geladen.")
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Fehler: Die Datei {INIT_FILE} wurde nicht gefunden. Alte Einstellungen bleiben erhalten.")
        except json.JSONDecodeError:
            logger.exception("[Fehler] Ungültiges JSON in %s",INIT_FILE)
            #return alte_einstellungen
        except Exception:
            logger.exception(
            "Unerwarteter Fehler beim Laden von %s. "
            "Alte Einstellungen bleiben erhalten.",INIT_FILE)
        return alte_einstellungen
    
    @staticmethod
    async def speichere_zugang(app_state, daten):
        async with app_state.save_lock:
            INIT_ZUGANG.parent.mkdir(parents=True, exist_ok=True)
            try:
                with INIT_ZUGANG.open("w", encoding="utf-8") as f:
                    json.dump(daten, f, indent=4, ensure_ascii=False)
                logger.info("Zugangs Daten gespeichert.")
            except Exception:
                logger.exception("Speicherfehler  beim Speichern der Zugangsdaten.")
    
    @staticmethod
    def lade_zugang(alte_einstellungen):
        """Lädt die Einstellungen aus IINIT_ZUGANG Bei Fehlern bleiben die alten Einstellungen erhalten."""
        try:
            with INIT_ZUGANG.open("r", encoding="utf-8") as f:
                logger.info(f" Zugang Einstellungen erfolgreich von  {INIT_ZUGANG} geladen.")
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Fehler: Die Datei {INIT_ZUGANG} wurde nicht gefunden. Alte Einstellungen bleiben erhalten.")
        except json.JSONDecodeError:
            logger.exception("[Fehler] Ungültiges JSON in %s", INIT_ZUGANG)
        except Exception:
            logger.exception(
            "Unerwarteter Fehler beim Laden von %s. "
            "Alte Einstellungen bleiben erhalten.", INIT_ZUGANG)
        return alte_einstellungen


class SshManager:
    """Kapselt das Starten, Stoppen und Prüfen des SSH-Servers."""

    @staticmethod
    def start(app_state):
        try:
            subprocess.run(["termux-wake-lock"])
            subprocess.Popen(["sshd"])
        except FileNotFoundError:
            logger.error("SSHD kann unter Windows nicht gestartet werden.")
        app_state.einstellungen["server_sshd"] = True

    @staticmethod
    def stop(app_state):
        try:
            subprocess.run(["pkill", "sshd"])
        except FileNotFoundError:
            logger.error("SSHD kann unter Windows nicht gestoppt werden.")
        app_state.einstellungen["server_sshd"] = False

    @staticmethod
    def laeuft(app_state):
        try:
            result = subprocess.run(["pgrep", "sshd"], stdout=subprocess.PIPE)
            return result.returncode == 0
        except FileNotFoundError:
            # Windows oder kein pgrep vorhanden
            return app_state.einstellungen.get("server_sshd", False)

