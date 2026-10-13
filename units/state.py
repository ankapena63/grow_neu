from __future__ import annotations
from collections import deque
import asyncio
import time
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from aiohttp import ClientSession
    from units.runner import AppRunner
    from units.history import HistoryManager
    from units.calculations import TageswerteManager
    from units.dazu import DazuManager
    from units.push import PushManager
    from units.configuration import SessionManager
    from units.unit_battery import GrowattSessionManager
    from units.unit_hms import Hms
    from units.unit_solax import Solax
    from units.unit_strom import Strom
    from units.unit_dose import DoseDevice, TuyaDoseManager

class AppState:
    growatt: GrowattSessionManager
    hms: Hms
    solax: Solax
    strom: Strom
    # Der Zustand speichert das Gerät typsicher ab, ohne dass state.py echten Code importiert
    #dose_device: Optional[DoseDevice] = None # ist unten
    def __init__(self):
        self.version: str = "13-10-2026"
        self.save_lock: asyncio.Lock = asyncio.Lock()

        # Gemeinsame Manager werden pro AppState genau einmal angelegt.
        # Typen werden nur unter TYPE_CHECKING importiert, damit keine
        # Laufzeit-Importzyklen zwischen state.py und den Managern entstehen.
        self._app_runner: AppRunner | None = None
        self._history_manager: HistoryManager | None = None
        self._tageswerte_manager: TageswerteManager | None = None
        self._dazu_manager: DazuManager | None = None
        self._push_manager: PushManager | None = None
        self._session_manager: SessionManager | None = None
        self.alle_daten: dict[str, dict[str, Any]] = {
            "akku": {},
            "hms": {},
            "solax": {},
            "strom": {},
            "dose": {}
        }
        self.roh: dict[str, dict[str, Any]] = {
            "tasmota": {"Fehler": "Noch keine daten"},
            "hms": {"Fehler": "Noch keine daten"},
            "akku_login": {"Fehler": "Noch kiene daten"},
            "akku_token": {"Fehler": "Noch keine daten"},
            "akku_status": {"Fehler": "Noch keine daten"},
            "solax_l": {"Fehler": "Noch kiene daten"},
            "solax_c": {"Fehler": "Noch keine daten"},
            "dose": {"Fehler": "Noch keine daten"},
            "sml": {"Fehler": "Noch keine daten"},
            "iobrocker": {"Fehler": "Noch keine daten"}
        }
        self.einstellungen: dict[str, Any] = {}
        self.zugang: dict[str, Any] = {}
        self.solax_local: dict[str, Any] = {}

        self.ppv_werte: deque[int | float] = deque(maxlen=2)
        self.solax_l_werte: deque[int | float] = deque(maxlen=3)
        self.solax_l_mittelwert: float = 0.0
        self.ppv_mittelwert: float = 0.0
        self.letzte_push_zeiten: dict[int, float] = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}
        # Historieneinträge bestehen aus (Unix-Zeitstempel, Messwert).
        self.aktuell_werte: dict[str, deque[tuple[float, Any]]] = {
            "strom": deque(maxlen=28800),
            "hms": deque(maxlen=28800),
            "solax": deque(maxlen=28800)
        }
        self.aktuell_letztes_speichern: float = 0.0
        self.aktuell_csv_letzter_zeitpunkt: dict[str, float] = {
            "strom": 0.0,
            "hms": 0.0,
            "solax": 0.0
        }

        # HTTP-Sessions werden zentral verwaltet und beim Start/Shutdown gesetzt.
        self.session_push: ClientSession | None = None
        self.session_hms: ClientSession | None = None
        self.session_tasmota: ClientSession | None = None
        self.session_solax_l: ClientSession | None = None
        self.session_strom: ClientSession | None = None
        self.session_solax_c: ClientSession | None = None
        self.session_growatt: ClientSession | None = None

        self.erste_abfrage: bool = True
        self.status_html: dict[str, dict[str, Any]] = {
            "hms": {"zeit_meine": 0, "takt": 10},
            "solax_l": {"zeit_meine": 0, "takt": 10},
            "solax_c": {"zeit_meine": 0, "takt": 10},
            "akku_token": {"zeit_meine": 0, "takt": 10},
            "akku_login": {"zeit_meine": 0, "takt": 10},
            "dose": {"zeit_meine": 0, "takt": 10},
            "strom": {"zeit_meine": 0, "takt": 10}
        }
        jetzt = time.monotonic()
        self.last_activity: float = jetzt
        self.start_akku: float = jetzt
        self.start_hms: float = jetzt
        self.start_solax_c: float = jetzt
        self.start_solax_l: float = jetzt
        self.start_strom: float = jetzt
        self.start_dazu_senden: float = jetzt
        self.takte: dict[str, int | float] = {}
        self.benutzer_activ: bool = False
        self.start_hms0: int = 10

        self.dazu: float = 0.0
        self.last_dose_check: float = 0.0
        self.dose_mode: str = "auto"
        self.dose_laeuft: bool = False
        self.dose_relay_state: bool | None = False
        self.dose_watt: float = 0.0
        self.dose_device: DoseDevice | None = None
        self._dose_manager: TuyaDoseManager | None = None

        self.is_shutting_down: bool = False
        self.kochen: bool = False
        self.kochen_zeit: float = 0.0
        self.kochen_end: float = 0.0

        self.dazu_intervall_start: float = 0.0
        self.dazu_intervall_dauer: float = 0.0
        self.dazu_intervall_ende: float = 0.0
        self.bool_dazu_intervall: bool = False
        self.akku_sanft_zeit: bool = False
        self.dazu_intervall: float = 0.0

        self.sonnenaufgang: str = "07:12:43"
        self.sonnenuntergang: str = "19:47:22"
        self.tageslange: str = "12:34:39"
        self.startnacht: str = "22:07"
        self.endnacht: str = "08:07"
        self.nachtzeit: bool = False

        self.dazu_sanft_soc: float = 0.0
        self.stunden_bis_nacht: float = 0.0
        self.brauche_watt: float = 0.0
        self.pro_stunde: float = 0.0

        self.akku_ppv_zustand: bool = False
        self.akku_entladen_zustand: bool = False
        self.temperature: float = 0.0
        self.soc: int = 0
        self.log_level: str = "INFO"

        self.takt_48_datei: int = 3600 * 2
        self.takt_48: int = 60

