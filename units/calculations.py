import logging
from astral import LocationInfo
from zoneinfo import ZoneInfo
from datetime import datetime, date, timedelta
from astral.sun import sun
import time
from units.config import FELDREIHENFOLGE
from units.configuration import EinstellungenManager
from units.history import TageshistorieManager
from units.state import AppState

logger = logging.getLogger(__name__)

class ZeitstempelManager:
    """Kapselt die Erzeugung einheitlicher Zeitstempel."""

    @staticmethod
    def zeitstempel():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")



class MittelwertManager:
    """Kapselt die laufende Mittelwertberechnung."""

    @staticmethod
    def mittelwert_get(wert, werte):
        if wert is not None:
            werte.append(wert)
        if not werte:
            return 0
        return sum(werte) / len(werte)


class SonnenManager:
    """Kapselt Sonnenaufgang, Sonnenuntergang und das Nachtfenster."""

    @staticmethod
    def astro_werte(app_state):
        aachen = LocationInfo(
            name="Aachen",
            region="Germany",
            timezone="Europe/Berlin",
            latitude=50.7753,
            longitude=6.0839,
        )
        s = sun(
            aachen.observer,
            date=date.today(),
            tzinfo=ZoneInfo("Europe/Berlin"),
        )
        sunrise = s["sunrise"]
        sunset = s["sunset"]
        app_state.sonnenaufgang = sunrise.strftime("%H:%M:%S")
        app_state.sonnenuntergang = sunset.strftime("%H:%M:%S")
        app_state.tageslange = str(sunset - sunrise).split(".")[0]

    @staticmethod
    def get_nachtzeten(app_state: AppState):
        try:
            sunrise_str = app_state.sonnenaufgang
            sunset_str = app_state.sonnenuntergang
            if sunrise_str and sunset_str:
                sunrise = datetime.strptime(sunrise_str, "%H:%M:%S")
                sunset = datetime.strptime(sunset_str, "%H:%M:%S")
                kor_aufgang = app_state.einstellungen.get("kor_aufgang", 0)
                kor_unter = app_state.einstellungen.get("kor_unter", 0)
                startnacht = sunset - timedelta(minutes=kor_unter)
                endnacht = sunrise + timedelta(minutes=kor_aufgang)
                app_state.startnacht = startnacht.strftime("%H:%M")
                app_state.endnacht = endnacht.strftime("%H:%M")
        except Exception:
            logger.exception("Nachtfenster konnte nicht berechnet werden")




class EnergiewerteManager:
    """Kapselt die Berechnung der Tages-, Monats- und Jahreswerte."""

    @staticmethod
    def get_heute_werte(daten, einst):
        werte = {}
        werte["datum"] = date.today().strftime("%d.%m.%Y")
        werte["tag_t"] = date.today().timetuple().tm_yday
        if "strom" in daten:
            if "Einspeise" in daten["strom"]:
                werte["einspeise_t"] = round(max(0, daten["strom"]["Einspeise"] - einst.get("einspeise_0", 0)), 2)
            if "Gesamt" in daten["strom"]:
                werte["gesamt_t"] = round(max(0, daten["strom"]["Gesamt"] - einst.get("gesamt_0", 0)), 3)
        if "hms" in daten:
            if "gesamt" in daten["hms"]:
                werte["hms_t"] = round(max(0, daten["hms"]["gesamt"] - einst.get("hms_0", 0)), 3)
        if "akku" in daten:
            if "eacTotal" in daten["akku"]:
                werte["growatt_t"] = round(max(0, daten["akku"]["eacTotal"] - einst.get("growatt_0", 0)), 3)
        if "solax" in daten:
            if "gesamt" in daten["solax"]:
                werte["solax_t"] = round(max(0, daten["solax"]["gesamt"] - einst.get("solax_0", 0)), 3)
        return werte

    @staticmethod
    def get_monats_werte(daten, einst):
        werte = {}
        werte["monat"] = date.today().month
        werte["einspeise"] = round(max(0, daten.get("strom", {}).get("Einspeise", 0) - einst.get("einspeise_monat_0", 0)), 2)
        werte["gesamt"] = round(max(0, daten.get("strom", {}).get("Gesamt", 0) - einst.get("gesamt_monat_0", 0)), 2)
        werte["hms"] = round(max(0, daten.get("hms", {}).get("gesamt", 0) - einst.get("hms_monat_0", 0)), 2)
        werte["growatt"] = round(max(0, daten.get("akku", {}).get("eacTotal", 0) - einst.get("growatt_monat_0", 0)), 2)
        werte["solax"] = round(max(0, daten.get("solax", {}).get("gesamt", 0) - einst.get("solax_monat_0", 0)), 2)
        return werte

    @staticmethod
    def get_jahres_werte(daten, einst):
        werte = {}
        werte["jahr"] = date.today().year
        werte["einspeise"] = round(max(0, daten.get("strom", {}).get("Einspeise", 0) - einst.get("einspeise_jahr_0", 0)), 2)
        werte["gesamt"] = round(max(0, daten.get("strom", {}).get("Gesamt", 0) - einst.get("gesamt_jahr_0", 0)), 2)
        werte["hms"] = round(max(0, daten.get("hms", {}).get("gesamt", 0) - einst.get("hms_jahr_0", 0)), 2)
        werte["growatt"] = round(max(0, daten.get("akku", {}).get("eacTotal", 0) - einst.get("growatt_jahr_0", 0)), 2)
        werte["solax"] = round(max(0, daten.get("solax", {}).get("gesamt", 0) - einst.get("solax_jahr_0", 0)), 2)
        return werte


class StatusManager:
    """Kapselt Status- und Verbrauchsberechnungen."""

    @staticmethod
    def status_aktualisieren(app_state, geraet, takt, zeit: bool = True):
        if geraet not in app_state.status_html:
            app_state.status_html[geraet] = {}
        if zeit:
            app_state.status_html[geraet]["zeit_meine"] = ZeitstempelManager.zeitstempel()
        app_state.status_html[geraet]["takt"] = takt

    @staticmethod
    def gereate_status(status_html):
        status = {}
        jetzt = time.time()
        for key, info in status_html.items():
            zeit = info.get("zeit_meine", 0)
            takt = info.get("takt", 10)
            if not zeit:
                status[key] = 0
                continue
            try:
                if isinstance(zeit, str):
                    zeit = datetime.strptime(
                        zeit, "%Y-%m-%d %H:%M:%S"
                    ).timestamp()
                diff = jetzt - zeit
                if diff < 0:
                    diff = 0
            except (ValueError, TypeError):
                status[key] = 0
                continue
            if diff > takt * 10:
                status[key] = 0
            elif diff <= takt:
                status[key] = 1
            elif diff <= takt * 4:
                status[key] = 2
            else:
                status[key] = 3
        return status

    @staticmethod
    def haus_verbrauch_get(app_state):
        solax = app_state.alle_daten.get("solax", {}).get("acpower", 0) or 0
        hms = app_state.alle_daten.get("hms", {}).get("aktuell", 0) or 0
        strom = app_state.alle_daten.get("strom", {}).get("Actuel", 0) or 0
        return round(solax + hms + strom)




class TageswerteManager:
    """Verwaltet Tages-, Monats- und Jahreswechsel für einen AppState."""

    def __init__(self, app_state: AppState):
        self.app_state = app_state

    @classmethod
    def fuer(cls, app_state: AppState) -> "TageswerteManager":
        """Liefert den gemeinsamen TageswerteManager dieses AppState."""
        manager = getattr(app_state, "_tageswerte_manager", None)
        if manager is None:
            manager = cls(app_state)
            app_state._tageswerte_manager = manager
        return manager

    async def reset_heute_werte(self) -> None:
        app_state = self.app_state
        letzter_reset = app_state.einstellungen.get("tag_0", 0)
        aktueller_tag = date.today().timetuple().tm_yday
        if letzter_reset == aktueller_tag:
            return
        heute = date.today()
        aktueller_monat = heute.month
        aktuelles_jahr = heute.year
        strom_daten = app_state.alle_daten.get("strom", {})
        hms_daten = app_state.alle_daten.get("hms", {})
        akku_daten = app_state.alle_daten.get("akku", {})
        solax_daten = app_state.alle_daten.get("solax", {})
        einspeise = strom_daten.get("Einspeise", 0)
        gesamt = strom_daten.get("Gesamt", 0)
        hms = hms_daten.get("gesamt", 0)
        akku = akku_daten.get("eacTotal", 0)
        solax = solax_daten.get("gesamt", 0)
        werte_alt = EnergiewerteManager.get_heute_werte(
            app_state.alle_daten,
            app_state.einstellungen,
        ) or {}
        werte_alt["datum"] = (
            date.today() - timedelta(days=1)
        ).strftime("%d.%m.%y")
        werte_alt["tag_t"] = letzter_reset
        datum_alt = heute - timedelta(days=1)
        werte_neu = {
            "datum": datum_alt.strftime("%d.%m.%y"),
            "tag_0": letzter_reset,
            "einspeise_0": einspeise,
            "gesamt_0": gesamt,
            "hms_0": hms,
            "growatt_0": akku,
            "solax_0": solax,
        }
        await TageshistorieManager.speichere_tageswerte(
            werte_neu,
            dateiname="tageswerte0.csv",
            feldreihenfolge=FELDREIHENFOLGE,
        )
        if app_state.einstellungen.get("monat_0") != aktueller_monat:
            logger.info("📅 Neuer Monat – Monatsstartwerte setzen")
            monat_start = {
                "monat_0": aktueller_monat,
                "einspeise_monat_0": einspeise,
                "gesamt_monat_0": gesamt,
                "hms_monat_0": hms,
                "growatt_monat_0": akku,
                "solax_monat_0": solax,
            }
            app_state.einstellungen.update(monat_start)
        if app_state.einstellungen.get("jahr_0") != aktuelles_jahr:
            logger.info("🎉 Neues Jahr – Jahresstartwerte setzen")
            jahr_start = {
                "jahr_0": aktuelles_jahr,
                "einspeise_jahr_0": einspeise,
                "gesamt_jahr_0": gesamt,
                "hms_jahr_0": hms,
                "growatt_jahr_0": akku,
                "solax_jahr_0": solax,
            }
            app_state.einstellungen.update(jahr_start)
        app_state.einstellungen.update(werte_neu)
        app_state.einstellungen["heute"] = date.today().strftime("%d.%m.%Y")
        app_state.einstellungen["tag_0"] = aktueller_tag
        SonnenManager.astro_werte(app_state)
        SonnenManager.get_nachtzeten(app_state)
        await EinstellungenManager.speichere_einstellungen(app_state, app_state.einstellungen)
        logger.info("Start neuerTag. Tagesstartwerte zurückgesetzt:")
        TageshistorieManager.rotate_logs()


def get_tageswerte_manager(app_state: AppState) -> TageswerteManager:
    """Kompatibler Einstiegspunkt; neue Aufrufer nutzen TageswerteManager.fuer."""
    return TageswerteManager.fuer(app_state)
