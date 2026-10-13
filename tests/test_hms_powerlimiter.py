import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from units.unit_hms import Hms


class HmsPowerControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_true_without_http_when_already_enabled(self):
        app_state = SimpleNamespace()
        limiter = Hms(app_state)

        with (
            patch.object(
                limiter,
                "lese_config",
                new=AsyncMock(return_value={"enabled": True}),
            ) as read_config,
            patch("units.unit_hms.SessionManager.fuer", return_value=SimpleNamespace(erstelle=AsyncMock())) as session_manager,
        ):
            result = await limiter.setze_powerlimiter(True)

        self.assertTrue(result)
        read_config.assert_awaited_once_with()
        session_manager.return_value.erstelle.assert_not_awaited()

    async def test_refuses_to_switch_inverter_when_not_reachable(self):
        app_state = SimpleNamespace(
            alle_daten={
                "hms": {
                    "serial": "serial-1",
                    "producing": False,
                    "reachable": False,
                },
            },
        )
        limiter = Hms(app_state)

        with patch("units.unit_hms.SessionManager.fuer", return_value=SimpleNamespace(erstelle=AsyncMock())) as session_manager:
            result = await limiter.schalte_wr(True)

        self.assertFalse(result)
        session_manager.return_value.erstelle.assert_not_awaited()
