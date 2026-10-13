from .config import DATA_DIR
import csv
from datetime import datetime, date
from collections import deque
import os
import shutil
import time
import logging

logger = logging.getLogger(__name__)


class HistoryManager:
    """Kapselt die Historien-Daten eines AppState."""

    def __init__(self, app_state):
        self.app_state = app_state

    @classmethod
    def fuer(cls, app_state):
        """Liefert den gemeinsamen HistoryManager dieses AppState."""
        manager = getattr(app_state, "_history_manager", None)
        if manager is None:
            manager = cls(app_state)
            app_state._history_manager = manager
        return manager

    async def speichere_aktuell_csv(self, dateiname="aktuell.csv"):
        pfad = DATA_DIR / dateiname
        app_state = self.app_state
        try:
            with pfad.open("w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["geraet", "zeit", "wert"])
                for geraet, werte in app_state.aktuell_werte.items():
                    for zeit, wert in werte:
                        if wert is None or zeit is None:
                            continue
                        writer.writerow([
                            geraet,
                            datetime.fromtimestamp(zeit).strftime("%d.%m.%y %H:%M:%S"),
                            wert,
                        ])
            logger.info("💾 aktuell.csv gespeichert")
        except Exception:
            logger.exception("⚠️ Fehler beim Speichern von aktuell.csv")

    async def lade_aktuell_csv(self, dateiname="aktuell.csv"):
        pfad = DATA_DIR / dateiname
        app_state = self.app_state
        if not pfad.is_file():
            logger.error("ℹ️ aktuell.csv nicht vorhanden")
            return
        for geraet in app_state.aktuell_werte:
            app_state.aktuell_werte[geraet].clear()
        grenze = time.time() - (48 * 60 * 60)
        try:
            with pfad.open("r", newline="", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                for zeile in reader:
                    geraet = zeile.get("geraet")
                    if geraet not in app_state.aktuell_werte:
                        continue
                    try:
                        zeit = datetime.strptime(
                            zeile["zeit"], "%d.%m.%y %H:%M:%S"
                        ).timestamp()
                        wert = float(zeile["wert"])
                    except (ValueError, TypeError, KeyError):
                        continue
                    if zeit < grenze:
                        continue
                    app_state.aktuell_werte[geraet].append((zeit, wert))
                    if zeit > app_state.aktuell_csv_letzter_zeitpunkt[geraet]:
                        app_state.aktuell_csv_letzter_zeitpunkt[geraet] = zeit
            logger.info("📂 Aktuell-Daten geladen")
        except Exception as ex:
            logger.error(f"⚠️ Fehler beim Laden von aktuell.csv: {ex}")

    def speichere_aktuell_wert(self, geraet, wert):
        app_state = self.app_state
        if geraet not in app_state.aktuell_werte or wert is None:
            return
        jetzt = time.time()
        daten = app_state.aktuell_werte[geraet]
        if isinstance(daten, list):
            daten = deque(daten)
            app_state.aktuell_werte[geraet] = daten
        if not daten:
            daten.append((jetzt, wert))
            return
        schleichen = daten[-1][1] is None
        if schleichen:
            if len(daten) > 1 and daten[-2][1] is not None:
                basis_zeitpunkt, basis_wert = daten[-2]
            else:
                daten.pop()
                schleichen = False
                basis_zeitpunkt, basis_wert = daten[-1]
        else:
            basis_zeitpunkt, basis_wert = daten[-1]
        unterschied = abs(wert - basis_wert)
        grenze = max(abs(basis_wert) * 0.05, 10)
        if unterschied < grenze:
            if not schleichen:
                daten.append((jetzt, wert))
                daten.append((jetzt, None))
            else:
                daten[-2] = (jetzt, wert)
        else:
            if schleichen:
                daten[-1] = (jetzt, wert)
            else:
                daten.append((jetzt, wert))
        grenze_zeit = jetzt - (48 * 60 * 60)
        while daten:
            zeit, _ = daten[0]
            if zeit is None or zeit < grenze_zeit:
                daten.popleft()
            else:
                break

    def schreibe_in_roh(self, key, daten):
        app_state = self.app_state
        if key not in app_state.roh or not isinstance(app_state.roh[key], dict):
            app_state.roh[key] = {}
        app_state.roh[key].clear()
        if isinstance(daten, dict):
            app_state.roh[key].update(daten)
        else:
            app_state.roh[key].update({"server_antwort": daten})


def get_history_manager(app_state):
    """Kompatibler Einstiegspunkt; neue Aufrufer nutzen HistoryManager.fuer."""
    return HistoryManager.fuer(app_state)


class TageshistorieManager:
    """Kapselt CSV-Tageshistorie und Logrotation."""

    @staticmethod
    async def speichere_tageswerte(
        werte: dict,
        dateiname: str = "tageswerte0.csv",
        feldreihenfolge: list = None,
    ):
        pfad = DATA_DIR / dateiname
        pfad.parent.mkdir(parents=True, exist_ok=True)
        if feldreihenfolge is None:
            feldreihenfolge = list(werte.keys())
        werte_vollstaendig = {
            key: werte.get(key, 0) for key in feldreihenfolge
        }
        existiert = os.path.isfile(pfad)
        with pfad.open("a", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=feldreihenfolge)
            if not existiert:
                writer.writeheader()
            writer.writerow(werte_vollstaendig)

    @staticmethod
    def rotate_logs():
        log_neu = "neu.log"
        log_vor = "neu_gestrn.log"
        log_alt = "neu_alt.log"
        try:
            if os.path.exists(log_vor):
                os.replace(log_vor, log_alt)
            if os.path.exists(log_neu):
                shutil.copy2(log_neu, log_vor)
            with open(log_neu, "w") as f:
                f.write(f"Log geleert am {datetime.now()}\\n")
            logger.info("Logrotation durchgeführt: %s", datetime.now())
        except Exception as e:
            logger.error("Fehler bei der Logrotation: %s", e)

    @staticmethod
    def lese_tageswerte0():
        pfad = DATA_DIR / "tageswerte0.csv"
        tageswerte = []
        if not pfad.exists():
            return tageswerte
        with pfad.open("r", encoding="utf-8", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            vorher = None
            for zeile in reader:
                try:
                    datum = datetime.strptime(zeile["datum"].strip(), "%d.%m.%y")
                    aktuelle = {
                        "einspeise": float(zeile["einspeise_0"]),
                        "gesamt": float(zeile["gesamt_0"]),
                        "hms": float(zeile["hms_0"]),
                        "growatt": float(zeile["growatt_0"]),
                        "solax": float(zeile["solax_0"]),
                    }
                except (ValueError, KeyError) as e:
                    logger.exception("[DIAGRAMM CSV FEHLER]: %s", e)
                    continue
                if all(wert == 0 for wert in aktuelle.values()):
                    continue
                if vorher is None:
                    vorher = aktuelle
                    continue
                tageswerte.append({
                    "datum": datum.strftime("%d.%m.%y"),
                    "jahr": datum.year,
                    "monat": datum.month,
                    "tag": datum.day,
                    "einspeise": round(max(0, aktuelle["einspeise"] - vorher["einspeise"]), 3),
                    "gesamt": round(max(0, aktuelle["gesamt"] - vorher["gesamt"]), 3),
                    "hms": round(max(0, aktuelle["hms"] - vorher["hms"]), 3),
                    "growatt": round(max(0, aktuelle["growatt"] - vorher["growatt"]), 3),
                    "solax": round(max(0, aktuelle["solax"] - vorher["solax"]), 3),
                })
                vorher = aktuelle
        return tageswerte
