from __future__ import annotations
from collections import deque
import asyncio
import time
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from units.unit_battery import GrowattSessionManager
    from units.unit_hms import Hms
    from units.unit_solax import Solax
    from units.unit_strom import Strom
    from units.unit_dose import DoseDevice , TuyaDoseManager

class AppState:
    growatt: GrowattSessionManager
    hms: Hms
    solax: Solax
    strom: Strom
    # Der Zustand speichert das Gerät typsicher ab, ohne dass state.py echten Code importiert
    #dose_device: Optional[DoseDevice] = None # ist unten
    def __init__(self):
        self.version = "10-10-2026"
        self.save_lock = asyncio.Lock()
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

        self.ppv_werte: deque[Any] = deque(maxlen=2)
        self.solax_l_werte: deque[Any] = deque(maxlen=3)
        self.solax_l_mittelwert = 0.0
        self.ppv_mittelwert = 0.0
        self.letzte_push_zeiten: dict[int, float] = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}
        self.aktuell_werte: dict[str, deque[Any]] = {
            "strom": deque(maxlen=28800),
            "hms": deque(maxlen=28800),
            "solax": deque(maxlen=28800)
        }
        self.aktuell_letztes_speichern = 0.0
        self.aktuell_csv_letzter_zeitpunkt: dict[str, float] = {
            "strom": 0.0,
            "hms": 0.0,
            "solax": 0.0
        }

        self.session_push = None
        self.session_hms = None
        self.session_tasmota = None
        self.session_solax_l = None
        self.session_strom = None
        self.session_solax_c = None
        self.session_growatt = None

        self.erste_abfrage = True
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
        self.last_activity = jetzt
        self.start_akku = jetzt
        self.start_hms = jetzt
        self.start_solax_c = jetzt
        self.start_solax_l = jetzt
        self.start_strom = jetzt
        self.start_dazu_senden = jetzt
        self.takte: dict[str, Any] = {}
        self.benutzer_activ = False
        self.start_hms0 = 10

        self.dazu = 0.0
        self.last_dose_check = 0.0
        self.dose_mode = "auto"
        self.dose_laeuft = False
        self.dose_relay_state = False
        self.dose_watt = 0.0
        self.dose_device: DoseDevice | None = None
        self._dose_manager: TuyaDoseManager | None = None

        self.is_shutting_down = False
        self.kochen = False
        self.kochen_zeit = 0.0
        self.kochen_end = 0.0

        self.dazu_intervall_start = 0.0
        self.dazu_intervall_dauer = 0.0
        self.dazu_intervall_ende = 0.0
        self.bool_dazu_intervall = False
        self.akku_sanft_zeit = False
        self.dazu_intervall = 0.0

        self.sonnenaufgang = "07:12:43"
        self.sonnenuntergang = "19:47:22"
        self.tageslange = "12:34:39"
        self.startnacht = "22:07"
        self.endnacht = "08:07"
        self.nachtzeit = False

        self.dazu_sanft_soc = 0.0
        self.stunden_bis_nacht = 0.0
        self.brauche_watt = 0.0
        self.pro_stunde = 0.0

        self.akku_ppv_zustand = False
        self.akku_entladen_zustand = False
        self.temperature = 0.0
        self.soc = 0
        self.log_level = "INFO"

        self.takt_48_datei = 3600 * 2
        self.takt_48 = 60

