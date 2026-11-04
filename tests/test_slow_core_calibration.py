"""The calibration must not mistake duty percentage for measured throughput."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from helpers import ROOT

sys.path.insert(0, str(Path(ROOT) / 'tools'))
import calibrate_slow_core as calibration


class CalibrationTests(unittest.TestCase):
    def test_both_native_kernels_must_meet_requested_range(self):
        self.assertTrue(calibration.check_target({'integer': .55, 'float': .60}))
        self.assertFalse(calibration.check_target({'integer': .54, 'float': .59}))
        self.assertFalse(calibration.check_target({'integer': .56, 'float': .61}))
        self.assertFalse(calibration.check_target({}))

    def test_partial_reservation_is_released_without_touching_other_owner(self):
        for sharing_denied in (False, True):
            with self.subTest(sharing_denied=sharing_denied), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for name in ('HEAVY.lock', 'HEAVY2.lock'):
                    (root / name).write_text('other owner')
                original = Path.open

                def lock_open(path, mode='r', *args, **kwargs):
                    if sharing_denied and mode == 'x' and path.exists():
                        raise PermissionError('existing owner still has the Windows lock open')
                    return original(path, mode, *args, **kwargs)

                with patch.object(Path, 'open', lock_open):
                    with self.assertRaisesRegex(RuntimeError, 'no timing was run'):
                        with calibration.TimingSlots('test', root):
                            self.fail('only one free slot')
                self.assertFalse((root / 'HEAVY3.lock').exists())
                self.assertEqual((root / 'HEAVY.lock').read_text(), 'other owner')
                self.assertEqual((root / 'HEAVY2.lock').read_text(), 'other owner')

    def test_pair_released_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, 'probe failed'):
                with calibration.TimingSlots('test', root) as slots:
                    self.assertEqual(len(slots.held), 2)
                    raise ValueError('probe failed')
            self.assertEqual(list(root.iterdir()), [])

        # A true write denial on the second reservation must unwind the first,
        # although __enter__ never returned and no context exit will run.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'HEAVY.lock').write_text('other owner')
            original = Path.open

            def deny_second(path, mode='r', *args, **kwargs):
                if mode == 'x' and path.name == 'HEAVY3.lock':
                    raise PermissionError('true directory write denial')
                return original(path, mode, *args, **kwargs)

            with patch.object(Path, 'open', deny_second):
                with self.assertRaisesRegex(PermissionError, 'true directory write denial'):
                    with calibration.TimingSlots('test', root):
                        self.fail('entry should fail')
            self.assertFalse((root / 'HEAVY2.lock').exists())
            self.assertFalse((root / 'HEAVY3.lock').exists())
            self.assertEqual((root / 'HEAVY.lock').read_text(), 'other owner')

    def test_cleanup_does_not_remove_replaced_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with calibration.TimingSlots('test', root) as slots:
                replaced = slots.held[0]
                replaced.write_text('new owner')
            self.assertEqual(replaced.read_text(), 'new owner')
            self.assertEqual(len(list(root.iterdir())), 1)


if __name__ == '__main__':
    unittest.main()
