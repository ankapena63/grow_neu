"""Erzeugt die Geräte-Manager für die Quart-Anwendung."""
from units.state import AppState
from units.unit_dose import TuyaDoseManager
from units.unit_hms import Hms
from units.unit_solax import Solax
from units.unit_strom import Strom


class DeviceFactory:
    """Kapselt die Initialisierung der Geräte eines AppState."""

    @staticmethod
    def initialisiere_geraete(app_state: AppState) -> None:
        """Initialisiert lokale Geräte genau einmal pro AppState.

        Growatt wird bewusst separat im Lifecycle erzeugt, nachdem die
        Zugangsdaten geladen wurden.
        """
        app_state.hms = Hms(app_state)
        app_state.solax = Solax(app_state)
        app_state.strom = Strom(app_state)

        # Genau eine Smart Dose für den vorhandenen AppState.
        app_state._dose_manager = TuyaDoseManager(app_state)


def initialisiere_geraete(app_state: AppState) -> None:
    """Kompatibilität für bestehende Aufrufer."""
    DeviceFactory.initialisiere_geraete(app_state)
