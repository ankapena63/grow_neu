import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from units.runner import sende_ntfy, sende_push


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

        result = await sende_ntfy(session, "Akku warm", 5)

        self.assertTrue(result)
        self.assertEqual(
            session.request,
            (
                "https://ntfy.sh/SolaxHmsGrowattvvv",
                b"Akku warm",
                {
                    "Priority": "5",
                    "Title": "Solar-Monitor",
                    "Tags": "warning",
                },
            ),
        )

    async def test_ntfy_client_reports_non_success_status(self):
        session = FakeSession(FakeResponse(503, "unavailable"))

        result = await sende_ntfy(session, "Test", 3)

        self.assertFalse(result)

    async def test_push_service_preserves_enabled_and_throttle_rules(self):
        app_state = SimpleNamespace(
            einstellungen={"nachricht_app": True},
            letzte_push_zeiten={},
        )
        notification_sender = AsyncMock(return_value=True)

        with (
            patch(
                "units.runner.mache_session",
                new_callable=AsyncMock,
            ) as make_session,
            patch(
                "units.runner.sende_ntfy",
                new=notification_sender,
            ),
            patch("units.runner.time.time", return_value=1000),
        ):
            await sende_push(app_state, "Test", pause=600, prio=4)
            await sende_push(app_state, "Test", pause=600, prio=4)

        make_session.assert_awaited_once_with(app_state, "session_push")
        notification_sender.assert_awaited_once()
        self.assertEqual(app_state.letzte_push_zeiten[4], 1000)
