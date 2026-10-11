from datetime import datetime

from units.state import AppState


class ZeitManager:
    def __init__(self, app_state: AppState):
        self.app_state = app_state

    def stunden_bis_nacht_get(self) -> float:
        app_state = self.app_state
        jetzt = datetime.now()
        max_s = app_state.einstellungen.get("max_soc", 99)
        soc = app_state.soc
        app_state.brauche_watt = round((max_s - soc) * app_state.einstellungen.get("watt_max", 4000) / 100, 2)
        app_state.pro_stunde = app_state.brauche_watt
        if app_state.nachtzeit:
            return 0.0
        heute = jetzt.strftime("%Y-%m-%d")
        start_zeit = datetime.strptime(f"{heute} {app_state.startnacht}", "%Y-%m-%d %H:%M")
        diff = start_zeit - jetzt
        stunden_bis_nacht = round(diff.total_seconds() / 3600, 2)
        if stunden_bis_nacht > 1:
            app_state.pro_stunde = round(app_state.brauche_watt / stunden_bis_nacht, 2)
        return stunden_bis_nacht

    def pruefe_dazu_intervall(self, zeit: float) -> None:
        app_state = self.app_state
        verbleibend = round(app_state.dazu_intervall_dauer * 60 - (zeit - app_state.dazu_intervall_start), 2)
        if verbleibend <= 0:
            app_state.dazu_intervall = 0.0
            app_state.bool_dazu_intervall = False
            app_state.akku_sanft_zeit = False
        else:
            app_state.dazu_intervall = round(verbleibend / 60, 2)
