import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run


class LauncherTests(unittest.TestCase):
    def test_platform_interpreter_paths(self):
        root = Path('environment')
        self.assertEqual(run.environment_python(root, 'win32'), root / 'Scripts' / 'python.exe')
        self.assertEqual(run.environment_python(root, 'darwin'), root / 'bin' / 'python')

    def test_cached_setup_avoids_pip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirements = root / 'requirements.txt'
            requirements.write_text('faster-whisper==1.2.1\n', encoding='utf-8')
            python = run.environment_python(root / '.venv')
            python.parent.mkdir(parents=True)
            python.touch()
            marker = root / '.venv' / 'requirements.sha256'
            marker.write_text(hashlib.sha256(requirements.read_bytes()).hexdigest().upper(), encoding='ascii')
            with patch.object(run.subprocess, 'run') as process:
                self.assertEqual(run.prepare(root), python)
                process.assert_not_called()

    def test_setup_failure_does_not_mark_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'requirements.txt').write_text('example', encoding='utf-8')
            python = run.environment_python(root / '.venv')
            python.parent.mkdir(parents=True)
            python.touch()
            with patch.object(run.subprocess, 'run', side_effect=RuntimeError('offline')):
                with self.assertRaises(RuntimeError):
                    run.prepare(root)
            self.assertFalse((root / '.venv' / 'requirements.sha256').exists())

    def test_arguments_and_exit_code_passthrough(self):
        with patch.object(run, 'prepare', return_value=Path('python')), patch.object(run.subprocess, 'run', return_value=SimpleNamespace(returncode=2)) as process:
            self.assertEqual(run.main(['--text', '/用户/文稿.txt', '--audio', '/用户/音频.mp3']), 2)
            command = process.call_args.args[0]
            self.assertEqual(command[-4:], ['--text', '/用户/文稿.txt', '--audio', '/用户/音频.mp3'])


if __name__ == '__main__':
    unittest.main()
