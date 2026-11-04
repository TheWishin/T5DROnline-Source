"""A launcher importing T5DR core must use T5DR's shipped build dependencies."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for sub in ('tools', 'lobby', 'launcher'):
    sys.path.insert(0, str(ROOT / sub))
import core


class BuildInterpreter(unittest.TestCase):
    def test_imported_release_uses_its_python_instead_of_host(self):
        with tempfile.TemporaryDirectory(prefix='T5 Spiel ') as folder:
            root = Path(folder) / 'Ł東京'
            python = root / 'python' / 'python.exe'
            python.parent.mkdir(parents=True)
            python.touch()
            host = str(Path(folder) / 'OpenRecomp' / 'portable' / 'pythonw.exe')
            with mock.patch.object(core, 'ROOT', str(root)), mock.patch.object(core.sys, 'executable', host):
                run = core.BuildRun('', '', str(root / 'native'), steps=['decrypt'])
            self.assertEqual(run.cmd[0], str(python))

    def test_developer_checkout_falls_back_to_host(self):
        with tempfile.TemporaryDirectory() as folder:
            host = os.path.join(folder, 'venv', 'python.exe')
            with mock.patch.object(core, 'ROOT', folder), mock.patch.object(core.sys, 'executable', host):
                run = core.BuildRun('', '', os.path.join(folder, 'native'), steps=['decrypt'])
            self.assertEqual(run.cmd[0], host)


if __name__ == '__main__':
    unittest.main()
