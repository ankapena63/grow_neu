import unittest
from unittest.mock import AsyncMock

from units.kochen_manager import KochenManager


class FakeAppState:
    def __init__(self):
        self.soc = 80
        self.einstellungen = {
            "kochen_soc_min": 30,
            "nacht_nur_0_schalter": False,
        }
        self.kochen = True
        self.kochen_zeit = 10.0
        self.kochen_end = 200.0
        self.nachtzeit = False


class KochenTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = FakeAppState()
        self.dazu_manager = AsyncMock()
        self.manager = KochenManager(self.state, self.dazu_manager)

    async def test_stops_when_soc_falls_below_minimum(self):
        self.state.soc = 29

        await self.manager.pruefe_kochen(zeit=100.0)

        self.assertFalse(self.state.kochen)
        self.assertEqual(self.state.kochen_zeit, 0.0)
        self.dazu_manager.rechne_dazu.assert_awaited_once_with()

    async def test_stops_when_time_has_expired(self):
        self.state.kochen_end = 100.0

        await self.manager.pruefe_kochen(zeit=100.0)

        self.assertFalse(self.state.kochen)
        self.assertEqual(self.state.kochen_zeit, 0.0)
        self.dazu_manager.rechne_dazu.assert_awaited_once_with()

    async def test_stops_at_night_when_only_zero_export_is_allowed(self):
        self.state.nachtzeit = True
        self.state.einstellungen["nacht_nur_0_schalter"] = True

        await self.manager.pruefe_kochen(zeit=100.0)

        self.assertFalse(self.state.kochen)
        self.assertEqual(self.state.kochen_zeit, 0.0)
        self.dazu_manager.rechne_dazu.assert_awaited_once_with()

    async def test_keeps_cooking_and_updates_remaining_minutes(self):
        self.state.kochen_end = 220.0

        await self.manager.pruefe_kochen(zeit=100.0)

        self.assertTrue(self.state.kochen)
        self.assertEqual(self.state.kochen_zeit, 2.0)
        self.dazu_manager.rechne_dazu.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
