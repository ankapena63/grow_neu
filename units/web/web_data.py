"""Gemeinsame Web-Daten für Dashboard, Einstellungen und API."""


from units.calculations import haus_verbrauch_get
from units.state import AppState


class WebDataManager:
    """Erstellt die gemeinsame Web-Datenstruktur an genau einer Stelle."""

    def get_web_daten(self, app_state: AppState) -> dict:
        return {
            "dazu": app_state.dazu,
            "haus_verbrauch": haus_verbrauch_get(app_state),
            "stunden_bis_nacht": app_state.stunden_bis_nacht,
            "brauche_watt": app_state.brauche_watt,
            "pro_stunde": app_state.pro_stunde,
            "akku_sanft_zeit": app_state.akku_sanft_zeit,
            "dazu_intervall": app_state.dazu_intervall,
            "dazu_sanft_soc": app_state.dazu_sanft_soc,
            "sonnenaufgang": app_state.sonnenaufgang,
            "sonnenuntergang": app_state.sonnenuntergang,
            "tageslange": app_state.tageslange,
            "startnacht": app_state.startnacht,
            "endnacht": app_state.endnacht,
            "nachtzeit": app_state.nachtzeit,
            "dose_mode": app_state.dose_mode,
            "dose_relay_state": app_state.dose_relay_state,
            "dose_watt": app_state.dose_watt,
            "solax_l_mittelwert": app_state.solax_l_mittelwert,
            "ppv_mittelwert": app_state.ppv_mittelwert,
            "temperature": app_state.temperature,
        }


web_data_manager = WebDataManager()
