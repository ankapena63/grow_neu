import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from units.unit_solax import Solax


class SolaxServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_cloud_polling_updates_state_when_due(self):
        state = SimpleNamespace(
            start_solax_c=10,
            start_solax_l=10,
            erste_abfrage=False,
            benutzer_activ=True,
            nachtzeit=False,
            takt_48=60,
            einstellungen={"takt_solax_c": 5, "takt_solax_l": 5},
            alle_daten={"solax": {"acpower": 12}},
            solax_local={},
        )
        service = Solax(state)
        service.abfrage_cloud = AsyncMock(return_value={"acpower": 40})

        with patch("units.unit_solax.StatusManager.status_aktualisieren"):
            await service.pruefe_cloud(20)

        service.abfrage_cloud.assert_awaited_once_with(
            {"acpower": 12},
            5,
        )
        self.assertEqual(state.alle_daten["solax"], {"acpower": 40})
        self.assertEqual(state.start_solax_c, 20)

    async def test_cloud_polling_skips_when_not_due(self):
        state = SimpleNamespace(
            start_solax_c=10,
            start_solax_l=10,
            erste_abfrage=False,
            benutzer_activ=True,
            nachtzeit=False,
            takt_48=60,
            einstellungen={"takt_solax_c": 5, "takt_solax_l": 5},
            alle_daten={"solax": {}},
            solax_local={},
        )
        service = Solax(state)
        service.abfrage_cloud = AsyncMock()

        with patch("units.unit_solax.StatusManager.status_aktualisieren"):
            await service.pruefe_cloud(14)

        service.abfrage_cloud.assert_not_awaited()

    async def test_local_polling_observes_existing_power_gate(self):
        state = SimpleNamespace(
            start_solax_c=10,
            start_solax_l=10,
            erste_abfrage=False,
            benutzer_activ=True,
            nachtzeit=False,
            takt_48=60,
            einstellungen={"takt_solax_c": 5, "takt_solax_l": 5},
            alle_daten={"solax": {"acpower": 0}},
            solax_local={},
        )
        service = Solax(state)
        service.abfrage_local = AsyncMock()

        with patch("units.unit_solax.StatusManager.status_aktualisieren"):
            await service.pruefe_local(20)

        service.abfrage_local.assert_not_awaited()
        self.assertEqual(state.start_solax_l, 10)
