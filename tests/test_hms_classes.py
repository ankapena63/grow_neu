import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from units.unit_hms import Hms


class FakeResponse:
    def __init__(self, data):
        self.data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    def raise_for_status(self):
        pass

    async def json(self):
        return self.data


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.request = None

    def get(self, url, *, timeout):
        self.request = (url, timeout)
        return self.response

    def post(self, url, *, data, timeout):
        self.request = (url, data, timeout)
        return self.response


class HmsClassTests(unittest.IsolatedAsyncioTestCase):
    async def test_hms_abfrage_uses_bound_state_and_parses_response(self):
        response_data = {
            "total": {
                "YieldDay": {"v": 12},
                "YieldTotal": {"v": 345},
                "Power": {"v": 50},
            },
            "inverters": [{
                "limit_absolute": 100,
                "producing": True,
                "reachable": True,
                "serial": "serial-1",
            }],
        }
        session = FakeSession(FakeResponse(response_data))
        state = SimpleNamespace(
            zugang={
                "ip_haupt": "http://192.168.1.",
                "ip_hms": 44,
                "hms_name": "user",
                "hms_pas": "pass",
            },
        )
        hms = Hms(state)
        with (
            patch(
                "units.unit_hms.SessionManager.fuer",
                return_value=SimpleNamespace(erstelle=AsyncMock(return_value=session)),
            ) as session_manager,
            patch("units.unit_hms.HistoryManager.fuer") as get_history,
            patch("units.unit_hms.StatusManager.status_aktualisieren") as update_status,
            patch("units.unit_hms.ZeitstempelManager.zeitstempel", return_value="now"),
        ):
            result = await hms.abfrage({"aktuell": 10}, 30)

        self.assertEqual(
            result,
            {
                "heute": 12,
                "gesamt": 345,
                "aktuell": 50,
                "limit": 100,
                "producing": True,
                "reachable": True,
                "takt": 30,
                "serial": "serial-1",
                "zeit_meine": "now",
            },
        )
        self.assertEqual(
            session.request[0],
            "http://192.168.1.44/api/livedata/status/inverters",
        )
        session_manager.return_value.erstelle.assert_awaited_once()
        get_history.return_value.schreibe_in_roh.assert_called_once_with("hms", response_data)
        update_status.assert_called_once_with(state, "hms", 30)

    async def test_setze_limit_posts_and_updates_state(self):
        response_data = {"type": "success"}
        session = FakeSession(FakeResponse(response_data))
        state = SimpleNamespace(
            zugang={
                "ip_haupt": "http://192.168.1.",
                "ip_hms": 44,
                "hms_name": "user",
                "hms_pas": "pass",
            },
            alle_daten={"hms": {"serial": "serial-1", "limit": 20}},
        )
        hms = Hms(state)

        with patch(
            "units.unit_hms.SessionManager.fuer",
            return_value=SimpleNamespace(erstelle=AsyncMock(return_value=session)),
        ) as session_manager:
            result = await hms.setze_limit(100)

        self.assertTrue(result)
        self.assertEqual(state.alle_daten["hms"]["limit"], 100)
        self.assertEqual(
            session.request[0],
            "http://192.168.1.44/api/limit/config",
        )
        session_manager.return_value.erstelle.assert_awaited_once()

    async def test_service_polls_when_due_and_records_current_value(self):
        state = SimpleNamespace(
            start_hms=10,
            start_hms0=10,
            erste_abfrage=False,
            benutzer_activ=True,
            nachtzeit=False,
            takt_48=60,
            alle_daten={"hms": {"aktuell": 5}},
            einstellungen={"aktuell_aktiv": True, "takt_hms": 5},
            hms=None,
        )
        service = Hms(state)
        state.hms = service
        service.abfrage = AsyncMock(return_value={"aktuell": 80})
        with (
            patch("units.unit_hms.StatusManager.status_aktualisieren"),
            patch("units.unit_hms.HistoryManager.fuer") as get_history,
        ):
            await service.pruefe(20)

        service.abfrage.assert_awaited_once_with(
            {"aktuell": 5},
            5,
        )
        self.assertEqual(state.alle_daten["hms"], {"aktuell": 80})
        self.assertEqual(state.start_hms, 20)
        get_history.return_value.speichere_aktuell_wert.assert_called_once_with("hms", 80)

    async def test_service_skips_poll_when_not_due(self):
        state = SimpleNamespace(
            start_hms=10,
            start_hms0=10,
            erste_abfrage=False,
            benutzer_activ=True,
            nachtzeit=False,
            takt_48=60,
            alle_daten={"hms": {}},
            einstellungen={"takt_hms": 5},
            hms=None,
        )
        service = Hms(state)
        state.hms = service
        service.abfrage = AsyncMock()

        with patch("units.unit_hms.StatusManager.status_aktualisieren"):
            await service.pruefe(14)

        service.abfrage.assert_not_awaited()

    async def test_limit_service_preserves_startup_delay_and_threshold(self):
        state = SimpleNamespace(
            start_hms0=0,
            hms=None,
            einstellungen={"hms_limit_soll": 100, "hms_bekommt_null": True},
            alle_daten={"hms": {"limit": 0}},
        )
        service = Hms(state)
        state.hms = service
        service.setze_limit = AsyncMock(return_value=True)

        await service.pruefe_limit(10)
        self.assertEqual(state.start_hms0, 1)
        service.setze_limit.assert_not_awaited()

        state.start_hms0 = 2
        await service.pruefe_limit(20)
        service.setze_limit.assert_awaited_once_with(100)
