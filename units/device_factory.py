"""Erzeugt die Geräteobjekte für die Quart-Anwendung."""
from units.state import AppState
from units.unit_battery import GrowattSessionManager
from units.unit_dose import TuyaDoseManager
from units.unit_hms import Hms
from units.unit_solax import Solax
from units.unit_strom import Strom


class DeviceFactory:
    """Kapselt die Initialisierung der Geräte eines AppState."""

    @staticmethod
    def initialisiere_geraete(app_state: AppState) -> None:
        """Initialisiert lokale Geräte und die einzelne Smart Dose."""
        app_state.hms = Hms(app_state)
        app_state.solax = Solax(app_state)
        app_state.strom = Strom(app_state)

        # Genau eine Smart Dose für den vorhandenen AppState.
        app_state._dose_manager = TuyaDoseManager(app_state)

    @staticmethod
    def initialisiere_growatt(app_state: AppState) -> None:
        """Erzeugt Growatt nach dem Laden der Zugangsdaten."""
        zugang = app_state.zugang
        app_state.growatt = GrowattSessionManager(
            zugang.get("username", ""),
            zugang.get("password", ""),
            zugang.get("deviceSn", ""),
            zugang.get("token", ""),
            app_state=app_state,
        )
