import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from units.unit_strom import Strom


class StromClassTests(unittest.IsolatedAsyncioTestCase):
    async def test_smart_query_uses_state_bound_session(self):
        class FakeResponse:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            def raise_for_status(self):
                pass

            async def json(self):
                return {"Actuel": 25}

        class FakeSession:
            def get(self, url, *, timeout):
                self.request = (url, timeout)
                return FakeResponse()

        state = SimpleNamespace(zugang={"ip_haupt": "http://host/"})
        client = Strom(state)
        session = FakeSession()

        with (
            patch(
                "units.unit_strom.SessionManager.fuer",
                return_value=SimpleNamespace(erstelle=AsyncMock(return_value=session)),
            ) as session_manager,
            patch("units.unit_strom.StatusManager.status_aktualisieren"),
            patch("units.unit_strom.ZeitstempelManager.zeitstempel", return_value="now"),
        ):
            result = await client.abfrage_smart({}, "smart-device", takt=10)

        self.assertEqual(result, {"Actuel": 25, "takt": 10, "zeit_meine": "now"})
        self.assertEqual(
            session.request[0],
            "http://host/smart-device/smartdaten",
        )
        session_manager.return_value.erstelle.assert_awaited_once_with("session_strom")

    async def test_service_polls_tasmota_and_updates_measurement_history(self):
        state = SimpleNamespace(
            start_strom=10,
            erste_abfrage=False,
            benutzer_activ=True,
            nachtzeit=False,
            takt_48=60,
            einstellungen={
                "abfrage_tasmota": True,
                "aktuell_aktiv": True,
                "takt_strom": 5,
            },
            alle_daten={"strom": {"Actuel": 5}},
            zugang={"ip_smart": "smart-device"},
        )
        service = Strom(state)
        service.abfrage_tasmota = AsyncMock(return_value={"Actuel": 60})
        service.abfrage_smart = AsyncMock()
        with (
            patch("units.unit_strom.StatusManager.status_aktualisieren"),
            patch("units.unit_strom.HistoryManager.fuer") as get_history,
        ):
            await service.pruefe(20)

        service.abfrage_tasmota.assert_awaited_once_with(
            {"Actuel": 5},
            5,
        )
        service.abfrage_smart.assert_not_awaited()
        self.assertEqual(state.alle_daten["strom"], {"Actuel": 60})
        self.assertEqual(state.start_strom, 20)
        get_history.return_value.speichere_aktuell_wert.assert_called_once_with("strom", 60)

    async def test_service_polls_smart_meter_when_tasmota_is_disabled(self):
        state = SimpleNamespace(
            start_strom=10,
            erste_abfrage=True,
            benutzer_activ=True,
            nachtzeit=False,
            takt_48=60,
            einstellungen={
                "abfrage_tasmota": False,
                "aktuell_aktiv": False,
                "takt_strom": 5,
            },
            alle_daten={"strom": {}},
            zugang={"ip_smart": "smart-device"},
        )
        service = Strom(state)
        service.abfrage_tasmota = AsyncMock()
        service.abfrage_smart = AsyncMock(return_value={"Actuel": 40})

        with patch("units.unit_strom.StatusManager.status_aktualisieren"):
            await service.pruefe(15)

        service.abfrage_smart.assert_awaited_once_with(
            {},
            "smart-device",
            5,
        )
        service.abfrage_tasmota.assert_not_awaited()
        self.assertEqual(state.alle_daten["strom"], {"Actuel": 40})
        self.assertEqual(state.start_strom, 15)

    async def test_service_skips_poll_when_not_due(self):
        state = SimpleNamespace(
            start_strom=10,
            erste_abfrage=False,
            benutzer_activ=True,
            nachtzeit=False,
            takt_48=60,
            einstellungen={"takt_strom": 5},
            alle_daten={"strom": {}},
            zugang={},
        )
        service = Strom(state)
        service.abfrage_tasmota = AsyncMock()
        service.abfrage_smart = AsyncMock()

        with patch("units.unit_strom.StatusManager.status_aktualisieren"):
            await service.pruefe(15)

        service.abfrage_tasmota.assert_not_awaited()
        service.abfrage_smart.assert_not_awaited()
