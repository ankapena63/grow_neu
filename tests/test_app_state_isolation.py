import unittest
from unittest.mock import patch

import neu


class FakeDoseDevice:
    def __init__(self):
        self.is_on = False
        self.actions = []

    def status(self):
        self.actions.append("status")
        return {"dps": {"1": self.is_on, "22": 456}}

    def turn_on(self):
        self.actions.append("on")
        self.is_on = True

    def turn_off(self):
        self.actions.append("off")
        self.is_on = False

    def set_version(self, version):
        pass

    def set_socketTimeout(self, timeout):
        pass

    def set_socketRetryLimit(self, limit):
        pass


class AppStateIsolationTests(unittest.TestCase):
    def test_each_app_gets_an_independent_state(self):
        app_one = neu.create_app()
        app_two = neu.create_app()

        state_one = app_one.extensions["app_state"]
        state_two = app_two.extensions["app_state"]

        self.assertIsNot(state_one, state_two)
        self.assertIsNot(state_one.save_lock, state_two.save_lock)
        self.assertIsNot(state_one.einstellungen, state_two.einstellungen)
        self.assertIsNot(state_one.alle_daten, state_two.alle_daten)

        state_one.dose_device = FakeDoseDevice()
        state_two.dose_device = FakeDoseDevice()
        self.assertIsNot(state_one.dose_device, state_two.dose_device)

        state_one.einstellungen["test_value"] = "one"
        state_one.alle_daten["dose"]["test_value"] = "one"

        self.assertNotIn("test_value", state_two.einstellungen)
        self.assertNotIn("test_value", state_two.alle_daten["dose"])


class DoseDeviceIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_relay_and_shutdown_only_use_their_app_device(self):
        app_one = neu.create_app()
        app_two = neu.create_app()

        state_one = app_one.extensions["app_state"]
        state_two = app_two.extensions["app_state"]
        self.assertIsNot(state_one._dose_manager, state_two._dose_manager)
        device_one = FakeDoseDevice()
        device_two = FakeDoseDevice()
        state_one.dose_device = device_one
        state_two.dose_device = device_two

        await state_one._dose_manager.relay_on()

        self.assertEqual(device_one.actions, ["on", "status"])
        self.assertEqual(device_two.actions, [])
        self.assertTrue(state_one.dose_relay_state)
        self.assertFalse(state_two.dose_relay_state)
        self.assertEqual(state_one.dose_watt, 45.6)
        self.assertEqual(state_two.dose_watt, 0.0)

        self.assertTrue(await state_one._dose_manager.shutdown())

        self.assertEqual(device_one.actions, ["on", "status", "off", "status"])
        self.assertEqual(device_two.actions, [])


    def test_managers_are_shared_per_state_but_isolated_between_apps(self):
        from units.dazu import DazuManager
        from units.history import HistoryManager
        from units.push import PushManager
        from units.runner import AppRunner

        app_one = neu.create_app()
        app_two = neu.create_app()
        state_one = app_one.extensions["app_state"]
        state_two = app_two.extensions["app_state"]

        # Growatt wird erst nach dem Laden der Zugangsdaten im Lifecycle erzeugt.
        # Für diesen reinen Manager-Test genügt ein Platzhalter-Gerät.
        state_one.growatt = object()
        state_two.growatt = object()

        runner_one = AppRunner.fuer(state_one)
        runner_two = AppRunner.fuer(state_two)

        self.assertIs(runner_one, AppRunner.fuer(state_one))
        self.assertIsNot(runner_one, runner_two)

        self.assertIs(runner_one.dazu_manager, DazuManager.fuer(state_one))
        self.assertIs(runner_one.history_manager, HistoryManager.fuer(state_one))
        self.assertIs(runner_one.history_manager, HistoryManager.fuer(state_one))

        self.assertIsNot(DazuManager.fuer(state_one), DazuManager.fuer(state_two))
        self.assertIsNot(HistoryManager.fuer(state_one), HistoryManager.fuer(state_two))
        self.assertIsNot(PushManager.fuer(state_one), PushManager.fuer(state_two))
        self.assertIs(PushManager.fuer(state_one), PushManager.fuer(state_one))



class GeraeteManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_device_failure_does_not_skip_the_other_devices(self):
        from units.geraete_manager import GeraeteManager

        class FakeDevice:
            def __init__(self, name, fail=False):
                self.name = name
                self.fail = fail
                self.calls = []

            async def pruefe(self, zeit):
                self.calls.append(zeit)
                if self.fail:
                    raise RuntimeError(f"{self.name} offline")

        app = neu.create_app()
        state = app.extensions["app_state"]
        growatt = FakeDevice("Growatt", fail=True)
        solax = FakeDevice("Solax")
        hms = FakeDevice("HMS")
        strom = FakeDevice("Strom")
        state.growatt = growatt
        state.solax = solax
        state.hms = hms
        state.strom = strom

        await GeraeteManager(state).pruefe_geraete(123.0)

        self.assertEqual(growatt.calls, [123.0])
        self.assertEqual(solax.calls, [123.0])
        self.assertEqual(hms.calls, [123.0])
        self.assertEqual(strom.calls, [123.0])



    async def test_uninitialized_device_does_not_skip_other_devices(self):
        from units.geraete_manager import GeraeteManager

        class FakeDevice:
            def __init__(self):
                self.calls = []

            async def pruefe(self, zeit):
                self.calls.append(zeit)

        app = neu.create_app()
        state = app.extensions["app_state"]
        growatt = FakeDevice()
        hms = FakeDevice()
        strom = FakeDevice()
        state.growatt = growatt
        state.solax = None
        state.hms = hms
        state.strom = strom

        await GeraeteManager(state).pruefe_geraete(321.0)

        self.assertEqual(growatt.calls, [321.0])
        self.assertEqual(hms.calls, [321.0])
        self.assertEqual(strom.calls, [321.0])

    async def test_dose_failure_is_contained_by_device_manager(self):
        from units.geraete_manager import GeraeteManager

        class BrokenDoseManager:
            async def pruefe(self, zeit):
                raise RuntimeError("Dose offline")

        app = neu.create_app()
        state = app.extensions["app_state"]
        state._dose_manager = BrokenDoseManager()

        # Der Fehler darf nicht aus dem Geräte-Manager herauslaufen.
        await GeraeteManager(state).pruefe_dose(123.0)


class RunnerResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_time_manager_errors_do_not_skip_device_polling(self):
        from units.runner import AppRunner

        class AsyncStep:
            async def reset_heute_werte(self):
                pass

        class BrokenTimeStep:
            def aktualisiere_zeitstatus(self, *args):
                raise RuntimeError("Zeitstatus-Testfehler")

            def pruefe_dazu_intervall(self, *args):
                raise RuntimeError("Intervall-Testfehler")

        class HistoryStep:
            async def pruefe_48st(self, zeit):
                pass

        class DeviceSteps:
            def __init__(self):
                self.dose_checked = False
                self.devices_checked = False

            async def pruefe_dose(self, zeit):
                self.dose_checked = True

            async def pruefe_geraete(self, zeit):
                self.devices_checked = True

        app = neu.create_app()
        state = app.extensions["app_state"]
        runner = AppRunner.fuer(state)
        runner.tageswerte_manager = AsyncStep()
        runner.zeit_manager = BrokenTimeStep()
        runner.history_manager = HistoryStep()
        devices = DeviceSteps()
        runner.geraete_manager = devices

        await runner.wiederholte_takt()

        self.assertTrue(devices.dose_checked)
        self.assertTrue(devices.devices_checked)
        self.assertFalse(state.erste_abfrage)

    async def test_history_and_cooking_errors_do_not_skip_device_polling(self):
        from units.runner import AppRunner

        class AsyncStep:
            async def reset_heute_werte(self):
                return None

            async def pruefe_48st(self, zeit):
                return None

        class ZeitStep:
            def aktualisiere_zeitstatus(self, *args):
                pass

            def pruefe_dazu_intervall(self, *args):
                pass

        class BrokenHistory:
            async def pruefe_48st(self, zeit):
                raise RuntimeError("Testfehler Historie")

        class BrokenCooking:
            async def pruefe_kochen(self, zeit):
                raise RuntimeError("Testfehler Kochsteuerung")

        class DeviceSteps:
            def __init__(self):
                self.dose_checked = False
                self.devices_checked = False

            async def pruefe_dose(self, zeit):
                self.dose_checked = True

            async def pruefe_geraete(self, zeit):
                self.devices_checked = True

        app = neu.create_app()
        state = app.extensions["app_state"]
        state.kochen = True
        runner = AppRunner.fuer(state)
        runner.tageswerte_manager = AsyncStep()
        runner.history_manager = BrokenHistory()
        runner.zeit_manager = ZeitStep()
        runner.kochen_manager = BrokenCooking()
        device_steps = DeviceSteps()
        runner.geraete_manager = device_steps

        await runner.wiederholte_takt()

        self.assertTrue(device_steps.dose_checked)
        self.assertTrue(device_steps.devices_checked)
        self.assertFalse(state.erste_abfrage)



class LifecycleCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_manager_rejects_new_sessions_after_shutdown(self):
        from unittest.mock import patch
        from units.configuration import SessionManager

        class FakeSession:
            def __init__(self):
                self.closed = False
                self.close_calls = 0

            async def close(self):
                self.close_calls += 1
                self.closed = True

        app = neu.create_app()
        state = app.extensions["app_state"]
        manager = SessionManager.fuer(state)
        session = FakeSession()
        manager._sessions["session_test"] = session

        with patch("units.configuration.aiohttp.ClientSession") as create_session:
            self.assertTrue(await manager.schliesse_alle())
            with self.assertRaisesRegex(RuntimeError, "nach dem Shutdown"):
                await manager.erstelle("session_neu")
            create_session.assert_not_called()

        self.assertTrue(session.closed)
        self.assertEqual(session.close_calls, 1)

        await manager.oeffne()
        self.assertFalse(manager._closed)

    async def test_reopening_session_manager_keeps_existing_sessions_tracked(self):
        from units.configuration import SessionManager

        class FakeSession:
            def __init__(self):
                self.closed = False
                self.close_calls = 0

            async def close(self):
                self.close_calls += 1
                self.closed = True

        app = neu.create_app()
        state = app.extensions["app_state"]
        manager = SessionManager.fuer(state)
        session = FakeSession()
        manager._sessions["session_test"] = session

        await manager.oeffne()

        # Ein erneutes Öffnen darf registrierte Sessions nicht aus der
        # Verwaltung entfernen; der nächste Shutdown muss sie schließen.
        self.assertIs(manager._sessions["session_test"], session)
        self.assertTrue(await manager.schliesse_alle())
        self.assertTrue(session.closed)
        self.assertEqual(session.close_calls, 1)

    async def test_growatt_and_sessions_are_closed_even_if_dose_shutdown_fails(self):
        from units.lifecycle import LifecycleManager
        from units.configuration import SessionManager

        class BrokenDose:
            async def shutdown(self):
                raise RuntimeError("Dose shutdown error")

        class FakeGrowatt:
            def __init__(self):
                self.closed = False

            async def close(self):
                self.closed = True

        class FakeSessions:
            def __init__(self):
                self.closed = False

            async def schliesse_alle(self):
                self.closed = True
                return True

        app = neu.create_app()
        state = app.extensions["app_state"]
        growatt = FakeGrowatt()
        sessions = FakeSessions()
        state._dose_manager = BrokenDose()
        state.growatt = growatt

        with patch.object(SessionManager, "fuer", return_value=sessions):
            result = await LifecycleManager().close_network_resources(state)

        self.assertFalse(result)
        self.assertTrue(growatt.closed)
        self.assertTrue(sessions.closed)


if __name__ == "__main__":
    unittest.main()
