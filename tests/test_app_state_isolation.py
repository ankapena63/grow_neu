import unittest

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


if __name__ == "__main__":
    unittest.main()
