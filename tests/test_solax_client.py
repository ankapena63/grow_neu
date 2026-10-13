import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp

from units.unit_solax import Solax


class SolaxDeviceTests(unittest.IsolatedAsyncioTestCase):
    async def test_cloud_query_uses_state_bound_session(self):
        class FakeResponse:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            def raise_for_status(self):
                pass

            async def json(self):
                return {
                    "success": True,
                    "result": {
                        "yieldtoday": 1.5,
                        "yieldtotal": 42,
                        "acpower": 150,
                    },
                }

        class FakeSession:
            def get(self, url, *, params, timeout):
                self.request = (url, params, timeout)
                return FakeResponse()

        state = SimpleNamespace(
            zugang={
                "solax_c_url": "https://solax.example/api",
                "solax_c_tokenId": "token",
                "solax_c_sn": "serial",
            }
        )
        client = Solax(state)
        session = FakeSession()

        with (
            patch(
                "units.unit_solax.SessionManager.fuer",
                return_value=SimpleNamespace(erstelle=AsyncMock(return_value=session)),
            ) as session_manager,
            patch("units.unit_solax.HistoryManager.fuer") as get_history,
            patch("units.unit_solax.StatusManager.status_aktualisieren"),
            patch("units.unit_solax.ZeitstempelManager.zeitstempel", return_value="now"),
        ):
            client.session_manager = session_manager.return_value
            client.history_manager = get_history.return_value
            result = await client.abfrage_cloud(
                {},
                60,
            )

        self.assertEqual(
            result,
            {
                "heute": 1.5,
                "gesamt": 42.0,
                "acpower": 150.0,
                "feedinpower": 0.0,
                "dc1": 0.0,
                "dc2": 0.0,
                "inverterStatus": "unbekannt",
                "upload_zeit": None,
                "takt": 60,
                "zeit_meine": "now",
            },
        )
        self.assertEqual(
            session.request[0],
            "https://solax.example/api",
        )
        self.assertEqual(session.request[1], {"tokenId": "token", "sn": "serial"})
        session_manager.return_value.erstelle.assert_awaited_once_with("session_solax_c")

    async def test_local_query_uses_serial_as_password_and_handles_disconnect(self):
        class FakeSession:
            def post(self, url, *, data, headers, timeout):
                self.request = (url, data, headers, timeout)
                raise aiohttp.ServerDisconnectedError("Server disconnected")

        state = SimpleNamespace(
            zugang={
                "solax_l_url": "http://solax.local",
                "solax_c_sn": "SERIAL",
            },
            solax_local={},
            solax_l_mittelwert=0,
        )
        client = Solax(state)
        session = FakeSession()

        with (
            patch(
                "units.unit_solax.SessionManager.fuer",
                return_value=SimpleNamespace(erstelle=AsyncMock(return_value=session)),
            ) as session_manager,
            patch("units.unit_solax.HistoryManager.fuer") as get_history,
            patch("units.unit_solax.MittelwertManager.mittelwert_get", return_value=25),
            patch("units.unit_solax.StatusManager.status_aktualisieren"),
            patch("units.unit_solax.ZeitstempelManager.zeitstempel", return_value="now"),
        ):
            client.session_manager = session_manager.return_value
            client.history_manager = get_history.return_value
            result = await client.abfrage_local(takt=60, versuche=1)

        self.assertEqual(
            session.request[1],
            "optType=ReadRealTimeData&pwd=SERIAL",
        )
        self.assertIn("fehler", result)
