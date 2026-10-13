import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from units.push import PushManager


class FakeResponse:
    def __init__(self, status, body=""):
        self.status = status
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def text(self):
        return self.body


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.request = None

    def post(self, url, *, data, headers):
        self.request = (url, data, headers)
        return self.response


class NotificationClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_ntfy_client_sends_expected_payload_and_headers(self):
        session = FakeSession(FakeResponse(200))
        result = await PushManager.sende_ntfy(session, "Akku warm", 5)
        self.assertTrue(result)
        self.assertEqual(session.request, (
            "https://ntfy.sh/SolaxHmsGrowattvvv",
            b"Akku warm",
            {"Priority": "5", "Title": "Solar-Monitor", "Tags": "warning"},
        ))

    async def test_ntfy_client_reports_non_success_status(self):
        session = FakeSession(FakeResponse(503, "unavailable"))
        result = await PushManager.sende_ntfy(session, "Test", 3)
        self.assertFalse(result)

    async def test_push_service_preserves_enabled_and_throttle_rules(self):
        app_state = SimpleNamespace(
            einstellungen={"nachricht_app": True},
            letzte_push_zeiten={},
        )
        manager = PushManager.fuer(app_state)
        notification_sender = AsyncMock(return_value=True)
        with (
            patch("units.push.SessionManager.fuer", return_value=SimpleNamespace(erstelle=AsyncMock())) as session_manager,
            patch.object(manager, "sende_ntfy", new=notification_sender),
            patch("units.push.time.time", return_value=1000),
        ):
            manager.session_manager = session_manager.return_value
            await manager.sende_push("Test", pause=600, prio=4)
            await manager.sende_push("Test", pause=600, prio=4)
        session_manager.return_value.erstelle.assert_awaited_once_with("session_push")
        notification_sender.assert_awaited_once()
        self.assertEqual(app_state.letzte_push_zeiten[4], 1000)


if __name__ == "__main__":
    unittest.main()
