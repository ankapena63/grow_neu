import asyncio
import os
from quart import Quart
import signal
from units.web import routes
from units.lifecycle import register_lifecycle
from units.state import AppState
from units.device_factory import initialisiere_geraete
from units.unit_dose import bp as dose_bp

def create_app():
    app = Quart(__name__)
    app_state = AppState()
    # Geräte zentral initialisieren
    initialisiere_geraete(app_state)
    # AppState für Web-Routen bereitstellen
    app.extensions["app_state"] = app_state
    app.extensions["server_shutdown_event"] = asyncio.Event()
    app.secret_key = (
        os.environ.get("QUART_SECRET_KEY")
        or os.environ.get("SECRET_KEY")
        or "geheimnis123"
    )
    app.register_blueprint(routes)
    app.register_blueprint(dose_bp)
    register_lifecycle(app)
    return app

app = create_app()


async def run_server() -> None:
    shutdown_event = app.extensions["server_shutdown_event"]
    loop = asyncio.get_running_loop()
    def handle_shutdown_signal(*_: object) -> None:
        loop.call_soon_threadsafe(shutdown_event.set)

    for signal_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        shutdown_signal = getattr(signal, signal_name, None)
        if shutdown_signal is None:
            continue
        try:
            loop.add_signal_handler(shutdown_signal, shutdown_event.set)
        except (NotImplementedError, RuntimeError):
            signal.signal(shutdown_signal, handle_shutdown_signal)

    print(f" * Running on http://0.0.0.0:5000 (Ctrl+C or web button to quit)")
    await app.run_task(
        host="0.0.0.0",
        port=5000,
        debug=False,
        shutdown_trigger=shutdown_event.wait,
    )
if __name__ == "__main__":
    asyncio.run(run_server())
    