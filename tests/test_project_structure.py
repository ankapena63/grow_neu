import asyncio
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import neu
from units.config import STANDARD_ZUGANG
from units import funkzii, routes
from units.services import calculations, configuration, history, integrations
from units.web import routes as web_routes


class ProjectStructureTests(unittest.TestCase):
    def test_credential_defaults_do_not_contain_secrets(self):
        credential_fields = (
            "token",
            "username",
            "password",
            "solax_c_tokenId",
            "hms_name",
            "hms_pas",
        )

        for field in credential_fields:
            with self.subTest(field=field):
                self.assertEqual(STANDARD_ZUGANG[field], "")

    def test_legacy_service_imports_forward_to_split_modules(self):
        self.assertIs(funkzii.astro_werte, calculations.astro_werte)
        self.assertIs(
            funkzii.lade_einstellungen,
            configuration.lade_einstellungen,
        )
        self.assertIs(
            funkzii.abfrage_solax_local,
            integrations.abfrage_solax_local,
        )
        self.assertIs(
            funkzii.speichere_aktuell_wert,
            history.speichere_aktuell_wert,
        )

    def test_legacy_route_import_keeps_original_blueprint_and_endpoints(self):
        expected_routes = {
            "routes.dashboard": ("/", {"GET"}),
            "routes.get_akku_cloud": ("/akku_cloud", {"GET"}),
            "routes.aktuell": ("/aktuell", {"GET"}),
            "routes.api_aktuell": ("/api/aktuell", {"GET"}),
            "routes.api_daten": ("/api/daten", {"GET"}),
            "routes.api_diagramm": ("/api/diagramm", {"GET"}),
            "routes.api_log": ("/api/log", {"GET"}),
            "routes.api_log_level": ("/api/log_level", {"POST"}),
            "routes.api_status": ("/api/stat", {"GET"}),
            "routes.toggle_aktuell": ("/api/toggle_aktuell", {"POST"}),
            "routes.diagramm": ("/dia", {"GET"}),
            "routes.einstellungen_seite": ("/einstellungen", {"GET"}),
            "routes.explorer": ("/explorer", {"GET"}),
            "routes.create_zip": ("/explorer/create_zip", {"POST"}),
            "routes.delete_item": ("/explorer/delete", {"POST"}),
            "routes.explorer_download": ("/explorer/download", {"GET"}),
            "routes.new_file": ("/explorer/new_file", {"POST"}),
            "routes.new_folder": ("/explorer/new_folder", {"POST"}),
            "routes.rename": ("/explorer/rename", {"POST"}),
            "routes.explorer_save": ("/explorer/save", {"POST"}),
            "routes.explorer_upload": ("/explorer/upload", {"POST"}),
            "routes.get_hms_800": ("/hms", {"GET"}),
            "routes.kochen_start": ("/kochen_start", {"POST"}),
            "routes.kochen_stop": ("/kochen_stop", {"POST"}),
            "routes.log_seite": ("/log", {"GET"}),
            "routes.get_parameter": ("/parameter", {"GET"}),
            "routes.get_parameter_zugang": ("/parameter_zugang", {"GET"}),
            "routes.roh": ("/roh", {"GET"}),
            "routes.server_sshd": ("/server_sshd", {"POST"}),
            "routes.shutdown_server": ("/shutdown", {"POST"}),
            "routes.confirm_shutdown": ("/shutdown/confirm", {"POST"}),
            "routes.get_sol_cloud": ("/solax_cloud", {"GET"}),
            "routes.get_local": ("/solax_local", {"GET"}),
            "routes.stat": ("/stat", {"GET"}),
            "routes.get_latest_status": ("/status", {"GET"}),
            "routes.get_strom": ("/strom", {"GET"}),
            "routes.get_tages": ("/tages", {"GET"}),
            "routes.tageswerte": ("/tageswerte", {"GET"}),
            "routes.update_settings": ("/update", {"POST"}),
            "routes.update_einstellung": ("/update_einstellung", {"POST"}),
            "routes.update_soc": ("/update_soc", {"POST"}),
            "routes.zugang": ("/zugang", {"GET", "POST"}),
            "dose.manual": ("/dose/manual", {"POST"}),
            "dose.set_mode": ("/dose/set_mode", {"POST"}),
            "dose.set_temps": ("/dose/set_temps", {"POST"}),
        }
        with patch("neu.create_dose_device", return_value=object()):
            app = neu.create_app()

        self.assertEqual(
            [hook.__name__ for hook in app.before_serving_funcs],
            ["init_daten"],
        )
        self.assertEqual(
            [hook.__name__ for hook in app.after_serving_funcs],
            ["shutdown"],
        )

        actual_routes = {
            rule.endpoint: (
                rule.rule,
                rule.methods - {"HEAD", "OPTIONS"},
            )
            for rule in app.url_map.iter_rules()
            if rule.endpoint != "static"
        }

        self.assertIs(routes.routes, web_routes)
        self.assertEqual(actual_routes, expected_routes)


class ExplorerRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_explorer_default_path_renders(self):
        client = neu.app.test_client()
        response = await client.get("/explorer")

        self.assertEqual(response.status_code, 200)
        html = await response.get_data(as_text=True)
        self.assertIn("📍 Pfad:", html)
        self.assertIn("static/explorer.css", html)
        self.assertIn("static/explorer.js", html)
        self.assertNotIn("<style", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("style=", html)

        for asset in ("explorer.css", "explorer.js"):
            with self.subTest(asset=asset):
                asset_response = await client.get(f"/static/{asset}")
                self.assertEqual(asset_response.status_code, 200)


class ServerShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_route_requests_graceful_server_shutdown(self):
        app = neu.create_app()
        shutdown_event = app.extensions["server_shutdown_event"]
        client = app.test_client()

        response = await client.post(
            "/shutdown",
            headers={"X-Shutdown-Handshake": "1"},
        )

        self.assertEqual(response.status_code, 202)
        self.assertFalse(shutdown_event.is_set())
        confirmation = await client.post("/shutdown/confirm")
        self.assertEqual(confirmation.status_code, 202)
        confirmation = await client.post("/shutdown/confirm")
        self.assertEqual(confirmation.status_code, 202)
        await asyncio.wait_for(shutdown_event.wait(), timeout=2)
        self.assertTrue(shutdown_event.is_set())

    async def test_settings_page_has_confirmable_shutdown_button(self):
        client = neu.app.test_client()

        response = await client.get("/einstellungen")

        self.assertEqual(response.status_code, 200)
        html = await response.get_data(as_text=True)
        self.assertIn('id="shutdownForm"', html)
        self.assertIn('action="/shutdown"', html)
        self.assertIn("window.confirm(", html)
        self.assertIn("Server beenden", html)


class DashboardAssetsTests(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_renders_with_external_assets(self):
        from units.web import dashboard as dashboard_routes

        with patch("neu.create_dose_device", return_value=object()):
            app = neu.create_app()

        state = app.extensions["app_state"]
        state.alle_daten["akku"] = {"soc": 0}
        state.einstellungen.update(
            {
                "intervall_takt": 4,
                "max_soc": 90,
                "max_limit": 800,
                "nur_nulleinspeisung": False,
                "akku_sanft": False,
                "akku_entladen": False,
                "akku_ppv": False,
                "dazu_sanft": 0,
                "mittel_verbrauch": 0,
                "ppv_soc_ab": 30,
                "nacht_nur_0_schalter": False,
                "heute": "04.10.2026",
                "tag_0": 4,
                "aktuell_aktiv": True,
            }
        )
        web_data = {
            "nachtzeit": False,
            "startnacht": "22:07",
            "endnacht": "08:07",
            "akku_sanft_zeit": False,
            "dazu_intervall": 0,
            "sonnenaufgang": "07:00",
            "tageslange": "12:00",
            "sonnenuntergang": "19:00",
        }
        period_data = {
            "einspeise": 0,
            "gesamt": 0,
            "growatt": 0,
            "hms": 0,
            "solax": 0,
        }

        with (
            patch.object(dashboard_routes, "run_sshd", return_value=False),
            patch.object(dashboard_routes, "get_web_daten", return_value=web_data),
            patch.object(dashboard_routes, "get_heute_werte", return_value={}),
            patch.object(dashboard_routes, "get_monats_werte", return_value=period_data),
            patch.object(dashboard_routes, "get_jahres_werte", return_value=period_data),
        ):
            client = app.test_client()
            response = await client.get("/")

        self.assertEqual(response.status_code, 200)
        html = await response.get_data(as_text=True)
        self.assertLess(html.index("static/dashboard.js"), html.index("</body>"))
        self.assertLess(html.index("</body>"), html.index("</html>"))
        self.assertNotIn("<script>", html)
        self.assertNotIn("<style", html)
        self.assertNotIn("style=", html)
        self.assertIn('data-toggle-status="an"', html)
        self.assertIn('data-next-status="true"', html)
        self.assertIn("strom-mode-mixed", html)
        self.assertIn(
            '<button type="button"\n             id="ssh-toggle"',
            html,
        )
        self.assertIn(
            '<button type="button"\n        id="switch-nacht-btn"',
            html,
        )
        self.assertIn('aria-pressed="false"', html)
        self.assertNotIn('<div id="ssh-toggle"', html)
        self.assertNotIn('<div id="switch-nacht-btn"', html)

        assets = (
            "dashboard.css",
            "dashboard.js",
            "strom-popover.js",
            "strom-speichern.js",
            "strom-steuerung.js",
            "strom-dialog.js",
            "akku-details.js",
            "akku-soc.js",
            "kochen.js",
        )
        for asset in assets:
            with self.subTest(asset=asset):
                asset_response = await client.get(f"/static/{asset}")
                self.assertEqual(asset_response.status_code, 200)


class SettingsAssetsTests(unittest.IsolatedAsyncioTestCase):
    async def test_settings_render_with_external_assets(self):
        client = neu.app.test_client()
        response = await client.get("/einstellungen")

        self.assertEqual(response.status_code, 200)
        html = await response.get_data(as_text=True)
        self.assertIn("static/settings.css", html)
        self.assertIn("static/settings.js", html)
        self.assertNotIn("<style", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("style=", html)

        for asset in ("settings.css", "settings.js"):
            with self.subTest(asset=asset):
                asset_response = await client.get(f"/static/{asset}")
                self.assertEqual(asset_response.status_code, 200)


class CdnDependencyTests(unittest.TestCase):
    def test_all_jsdelivr_npm_dependencies_are_version_pinned(self):
        template_dir = neu.app.template_folder
        self.assertIsNotNone(template_dir)
        versions = {}
        pattern = re.compile(
            r"https://cdn\.jsdelivr\.net/npm/([^/@\" ]+)"
            r"(?:@([^/\" ]+))?"
        )

        for template_path in Path(template_dir).glob("*.html"):
            html = template_path.read_text(encoding="utf-8")
            for package, version in pattern.findall(html):
                self.assertTrue(
                    version,
                    f"{package} in {template_path.name} must pin an exact version",
                )
                versions.setdefault(package, set()).add(version)

        self.assertEqual(
            versions,
            {
                "bootstrap": {"5.3.3"},
                "chart.js": {"4.4.7"},
                "luxon": {"3.5.0"},
                "chartjs-adapter-luxon": {"1.3.1"},
                "hammerjs": {"2.0.8"},
                "chartjs-plugin-zoom": {"2.2.0"},
            },
        )


if __name__ == "__main__":
    unittest.main()
