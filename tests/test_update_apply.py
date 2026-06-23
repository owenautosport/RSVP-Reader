import os
import tempfile
import unittest
from pathlib import Path

from rsvp.update.apply import (
    LinuxApplier,
    MacApplier,
    WindowsApplier,
    can_self_apply,
    get_applier,
)


class GetApplierTests(unittest.TestCase):
    def test_maps_each_known_os(self):
        self.assertIsInstance(get_applier("Windows"), WindowsApplier)
        self.assertIsInstance(get_applier("Darwin"), MacApplier)
        self.assertIsInstance(get_applier("Linux"), LinuxApplier)

    def test_unknown_os_applier_refuses(self):
        applier = get_applier("Plan9")
        with self.assertRaises(Exception):
            applier.apply(Path("/tmp/whatever"))


class CanSelfApplyTests(unittest.TestCase):
    def test_false_when_running_from_source(self):
        # The test runner is plain CPython, not a frozen bundle.
        self.assertFalse(can_self_apply())


class WindowsApplierTests(unittest.TestCase):
    def test_runs_installer_silently_then_exits(self):
        calls = {}
        ap = WindowsApplier(
            runner=lambda cmd: calls.setdefault("cmd", cmd),
            exiter=lambda: calls.setdefault("exited", True),
        )
        ap.apply(Path("C:/Downloads/Setup.exe"))
        self.assertEqual(calls["cmd"], ["C:/Downloads/Setup.exe", "/S"])
        self.assertTrue(calls["exited"])


class LinuxApplierTests(unittest.TestCase):
    def test_replaces_appimage_in_place_and_relaunches(self):
        tmp = Path(tempfile.mkdtemp())
        current = tmp / "RSVP.AppImage"
        current.write_bytes(b"OLD")
        downloaded = tmp / "new.AppImage"
        downloaded.write_bytes(b"NEW")
        relaunched = {}
        ap = LinuxApplier(
            appimage_path=str(current),
            execv=lambda path, argv: relaunched.update(path=path),
        )
        ap.apply(downloaded)
        self.assertEqual(current.read_bytes(), b"NEW")
        self.assertTrue(os.access(current, os.X_OK))
        self.assertEqual(relaunched["path"], str(current))


class MacApplierTests(unittest.TestCase):
    def test_hands_off_to_helper_referencing_the_dmg_then_exits(self):
        calls = {}
        ap = MacApplier(
            runner=lambda cmd: calls.setdefault("cmd", cmd),
            exiter=lambda: calls.setdefault("exited", True),
            app_path="/Applications/RSVP.app",
        )
        ap.apply(Path("/tmp/RSVP-macOS.dmg"))
        # dmg is passed as a positional arg, not interpolated into the script.
        self.assertIn("/tmp/RSVP-macOS.dmg", calls["cmd"])
        self.assertTrue(calls["exited"])

    def test_malicious_dmg_path_is_not_injected_into_command(self):
        calls = {}
        ap = MacApplier(
            runner=lambda cmd: calls.setdefault("cmd", cmd),
            exiter=lambda: None,
            app_path="/Applications/RSVP.app",
        )
        # A maliciously named asset: shell metacharacters + a double quote.
        evil = '/tmp/x";rm -rf ~;echo ".dmg'
        ap.apply(Path(evil))
        # The dmg is referenced verbatim as its own argv entry (safe)...
        self.assertIn(evil, calls["cmd"])
        # ...but the script text must NOT contain the injected payload, i.e. the
        # value is never spliced into the /bin/sh -c script string.
        script = calls["cmd"][2]
        self.assertNotIn("rm -rf ~", script)
        self.assertNotIn(evil, script)

    def test_refuses_when_no_valid_app_target(self):
        ap = MacApplier(
            runner=lambda cmd: None,
            exiter=lambda: None,
            app_path="",  # no determinable .app bundle
        )
        with self.assertRaises(Exception):
            ap.apply(Path("/tmp/RSVP-macOS.dmg"))


if __name__ == "__main__":
    unittest.main()
