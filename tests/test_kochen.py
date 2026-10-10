import unittest
from unittest.mock import AsyncMock, patch

from units.runner import pruefe_kochen


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
    async def test_stops_when_soc_falls_below_minimum(self):
        state = FakeAppState()
        state.soc = 29

        with patch("units.runner.rechne_dazu", new_callable=AsyncMock) as recalc:
            await pruefe_kochen(state, zeit=100.0)

        self.assertFalse(state.kochen)
        self.assertEqual(state.kochen_zeit, 0.0)
        recalc.assert_awaited_once_with(state)

    async def test_stops_when_time_has_expired(self):
        state = FakeAppState()
        state.kochen_end = 100.0

        with patch("units.runner.rechne_dazu", new_callable=AsyncMock) as recalc:
            await pruefe_kochen(state, zeit=100.0)

        self.assertFalse(state.kochen)
        self.assertEqual(state.kochen_zeit, 0.0)
        recalc.assert_awaited_once_with(state)

    async def test_stops_at_night_when_only_zero_export_is_allowed(self):
        state = FakeAppState()
        state.nachtzeit = True
        state.einstellungen["nacht_nur_0_schalter"] = True

        with patch("units.runner.rechne_dazu", new_callable=AsyncMock) as recalc:
            await pruefe_kochen(state, zeit=100.0)

        self.assertFalse(state.kochen)
        self.assertEqual(state.kochen_zeit, 0.0)
        recalc.assert_awaited_once_with(state)

    async def test_keeps_cooking_and_updates_remaining_minutes(self):
        state = FakeAppState()
        state.kochen_end = 220.0

        with patch("units.runner.rechne_dazu", new_callable=AsyncMock) as recalc:
            await pruefe_kochen(state, zeit=100.0)

        self.assertTrue(state.kochen)
        self.assertEqual(state.kochen_zeit, 2.0)
        recalc.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
