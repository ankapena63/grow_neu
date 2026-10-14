import asyncio
import os
import signal

from quart import Quart

from units.web import routes
from units.lifecycle import LifecycleManager
from units.state import AppState
from units.device_factory import DeviceFactory
from units.unit_dose import bp as dose_bp


class ApplicationManager:
    """Verwaltet die Anwendung und den Serverstart."""

    def __init__(self):
        self.app = None
        self.lifecycle_manager = LifecycleManager()

    def create_app(self):
        """Erstellt und initialisiert die Quart-Anwendung."""
        app = Quart(__name__)
        app_state = AppState()

        # Geräte zentral initialisieren
        DeviceFactory.initialisiere_geraete(app_state)

        # AppState für Web-Routen bereitstellen
        app.extensions["app_state"] = app_state
        app.extensions["server_shutdown_event"] = asyncio.Event()

        app.secret_key = (
            os.environ.get("QUART_SECRET_KEY")
            or os.environ.get("SECRET_KEY")
            or os.urandom(32)
        )

        app.register_blueprint(routes)
        app.register_blueprint(dose_bp)

        self.lifecycle_manager.register(app)

        self.app = app
        return app

    async def run_server(self) -> None:
        """Startet den Server und behandelt Beendigungssignale."""
        if self.app is None:
            raise RuntimeError(
                "Die Anwendung wurde noch nicht erstellt."
            )

        app = self.app
        shutdown_event = app.extensions["server_shutdown_event"]
        loop = asyncio.get_running_loop()

        def handle_shutdown_signal(*_: object) -> None:
            loop.call_soon_threadsafe(shutdown_event.set)

        for signal_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            shutdown_signal = getattr(signal, signal_name, None)

            if shutdown_signal is None:
                continue

            try:
                loop.add_signal_handler(
                    shutdown_signal,
                    shutdown_event.set,
                )
            except (NotImplementedError, RuntimeError):
                signal.signal(
                    shutdown_signal,
                    handle_shutdown_signal,
                )

        print(
            " * Running on http://0.0.0.0:5000 "
            "(Ctrl+C or web button to quit)"
        )

        await app.run_task(
            host="0.0.0.0",
            port=5000,
            debug=False,
            shutdown_trigger=shutdown_event.wait,
        )


# Ein gemeinsamer Manager für die Anwendung
application_manager = ApplicationManager()


def create_app():
    """Kompatibilität für bisherige Aufrufer."""
    return application_manager.create_app()


app = create_app()


if __name__ == "__main__":
    asyncio.run(application_manager.run_server())
