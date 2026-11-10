"""Battery warning before Play and Build (launcher/core.py battery_warning, t5dr_launcher.pyw battery_notice).

On battery with a power setting that holds the processor back the launcher says "plug in the charger" and goes on;
on AC it says nothing. The power source is a fake one: this PC's real state is never read.
"""
import importlib.machinery
import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "launcher"))
sys.path.insert(0, str(ROOT / "lobby"))

TEXT = "Plug in the charger so the sound does not crackle."
BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"


def load_launcher():
    loader = importlib.machinery.SourceFileLoader("launcher_battery_probe", str(ROOT / "launcher/t5dr_launcher.pyw"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class BatteryWarning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher = load_launcher()

    def press(self, button, status, plan, mode):
        """Press Play or Build with a fake power source -> (texts shown, what started)."""
        L = self.launcher
        core = L.core
        shown, started = [], []

        def fake_warning():
            return real(status=status, plan=plan, mode=mode)

        real = core.battery_warning
        box = L.dialogs.show_info
        core.battery_warning = fake_warning
        L.dialogs.show_info = lambda _title, message, parent=None: shown.append(message)
        try:
            app = types.SimpleNamespace(start_game=lambda: started.append("game"),
                                        start_build=lambda: started.append("build"))
            for name in ("battery_notice", "play", "build_clicked"):
                setattr(app, name, types.MethodType(getattr(L.App, name), app))
            getattr(app, button)()
        finally:
            core.battery_warning, L.dialogs.show_info = real, box
        return shown, started

    def test_shown_on_battery_and_not_on_ac(self):
        eff = self.launcher.core.POWER_MODE_EFFICIENCY
        on_battery = (False, 60, True, False)       # (ac, percent, has_battery, battery_saver)
        on_ac = (True, 60, True, False)
        desktop = (True, None, False, False)
        for button, what in (("play", "game"), ("build_clicked", "build")):
            with self.subTest(button=button):
                # on battery, "Best power efficiency": the warning, and the game / build still starts
                self.assertEqual(self.press(button, on_battery, BALANCED, eff), ([TEXT], [what]))
                # the same laptop on its charger, and a desktop: nothing
                self.assertEqual(self.press(button, on_ac, BALANCED, eff), ([], [what]))
                self.assertEqual(self.press(button, desktop, BALANCED, eff), ([], [what]))
                # on battery with a power mode that does not hold the processor back: nothing
                self.assertEqual(self.press(button, on_battery, BALANCED, ""), ([], [what]))
        core = self.launcher.core
        self.assertEqual(core.battery_warning(status=(False, 60, True, True), plan=BALANCED, mode=""), TEXT)
        self.assertEqual(core.battery_warning(status=on_battery, plan=core.POWER_SAVER_PLAN, mode=""), TEXT)
        self.assertIsNone(core.battery_warning(status=(None, None, False, False), plan=BALANCED, mode=eff))
        from t5lobby import i18n_de
        self.assertEqual(i18n_de.MESSAGES[TEXT], "Netzteil anschließen, damit der Ton nicht knackt.")


if __name__ == "__main__":
    unittest.main()
