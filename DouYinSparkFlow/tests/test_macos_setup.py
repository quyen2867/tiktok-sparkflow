"""Startup checks without opening TikTok or downloading browsers."""
import importlib.metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from core import browser
from scripts import check_macos_setup as setup


class BrowserSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sparkflow setup ')
        self.addCleanup(self.temp.cleanup)
        self.executable = Path(self.temp.name) / 'Brave Browser'
        self.executable.touch()
        self.executable.chmod(0o755)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.brave = patch.object(browser, 'BRAVE_EXECUTABLE', self.executable)
        self.brave.start()
        self.addCleanup(self.brave.stop)

    def test_macos_prefers_brave(self):
        with patch.object(sys, 'platform', 'darwin'):
            self.assertEqual(str(self.executable), browser._browser_launch_options()['executable_path'])

    def test_missing_brave_falls_back_to_playwright(self):
        self.executable.unlink()
        with patch.object(sys, 'platform', 'darwin'):
            self.assertNotIn('executable_path', browser._browser_launch_options())

    def test_non_executable_brave_falls_back(self):
        self.executable.chmod(0o644)
        with patch.object(sys, 'platform', 'darwin'):
            self.assertNotIn('executable_path', browser._browser_launch_options())

    def test_non_macos_unchanged(self):
        with patch.object(sys, 'platform', 'linux'):
            self.assertNotIn('executable_path', browser._browser_launch_options())

    def test_explicit_executable_wins_over_channel_and_brave(self):
        with patch.dict(os.environ, SPARKFLOW_BROWSER_EXECUTABLE='/chosen/browser', SPARKFLOW_BROWSER_CHANNEL='chrome'):
            opts = browser._browser_launch_options()
            self.assertEqual('/chosen/browser', opts['executable_path'])
            self.assertNotIn('channel', opts)

    def test_explicit_channel_wins_over_brave(self):
        with patch.dict(os.environ, SPARKFLOW_BROWSER_CHANNEL='chrome'):
            opts = browser._browser_launch_options()
            self.assertEqual('chrome', opts['channel'])
            self.assertNotIn('executable_path', opts)

    def test_preflight_brave_skips_playwright_download(self):
        with patch.dict(os.environ, SPARKFLOW_BROWSER_EXECUTABLE=str(self.executable)), patch.object(setup.subprocess, 'run') as run:
            setup.main()
            run.assert_not_called()

    def test_preflight_bad_override_explains_error(self):
        with patch.dict(os.environ, SPARKFLOW_BROWSER_EXECUTABLE='/missing/browser'):
            with self.assertRaisesRegex(RuntimeError, 'SPARKFLOW_BROWSER_EXECUTABLE'):
                setup.main()

    def test_missing_dependency_explains_install_command(self):
        with patch.object(importlib.metadata, 'version', side_effect=importlib.metadata.PackageNotFoundError):
            with self.assertRaisesRegex(RuntimeError, 'pip install -r DouYinSparkFlow/requirements.txt'):
                setup.main()

    def test_chromium_cached_or_installed_in_effective_location(self):
        self.executable.unlink()
        with patch('playwright.sync_api.sync_playwright') as start, patch.object(setup.subprocess, 'run') as run:
            start.return_value.__enter__.return_value.chromium.executable_path = str(self.executable)
            def install(*args, **kwargs):
                self.executable.touch()
                self.executable.chmod(0o755)
            run.side_effect = install
            setup.main()
            run.assert_called_once_with([sys.executable, '-m', 'playwright', 'install', 'chromium'], check=True)
            run.reset_mock()
            setup.main()
            run.assert_not_called()

    def test_failed_download_stops_startup(self):
        self.executable.unlink()
        with patch('playwright.sync_api.sync_playwright') as start, patch.object(setup.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'playwright')):
            start.return_value.__enter__.return_value.chromium.executable_path = str(self.executable)
            with self.assertRaises(subprocess.CalledProcessError):
                setup.main()


class ShellStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sparkflow repo with spaces ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / 'DouYinSparkFlow'
        (self.app / 'scripts').mkdir(parents=True)
        self.script = self.app / 'scripts/start_macos.sh'
        shutil.copy2(Path(__file__).resolve().parents[1] / 'scripts/start_macos.sh', self.script)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('SPARKFLOW_')}

    def run_script(self):
        return subprocess.run(['bash', str(self.script)], cwd=self.root, env=self.env, text=True, capture_output=True, timeout=15)

    def test_missing_venv_stops_with_instructions(self):
        result = self.run_script()
        self.assertNotEqual(0, result.returncode)
        self.assertIn('python3.11 -m venv', result.stderr)

    def test_old_python_stops_before_services(self):
        # Execute the real version-check code with an emulated 3.9 interpreter.
        old = self.root / 'old-python'
        old.write_text('#!' + sys.executable + '\nimport sys\nsys.version_info = (3, 9, 6)\nsys.version = "3.9.6"\nexec(sys.argv[2])\n')
        old.chmod(0o755)
        self.env['SPARKFLOW_PYTHON'] = str(old)
        result = self.run_script()
        self.assertNotEqual(0, result.returncode)
        self.assertIn('Cần Python >=3.11; đang dùng 3.9.6', result.stderr)
        self.assertFalse((self.app / 'logs').exists())

    def test_relative_python_spaces_and_browser_environment_reach_both_services(self):
        (self.root / '.venv/bin').mkdir(parents=True)
        (self.root / '.venv/bin/python').symlink_to(sys.executable)
        self.env['SPARKFLOW_PYTHON'] = '.venv/bin/python'
        self.env['SPARKFLOW_BROWSER_EXECUTABLE'] = '/test/Brave Browser'
        (self.app / 'scripts/check_macos_setup.py').write_text('')
        payload = 'import os\nfrom pathlib import Path\nassert os.environ["SPARKFLOW_BROWSER_EXECUTABLE"] == "/test/Brave Browser"\nassert os.environ["SPARKFLOW_BROWSER_HEADFUL"] == "1"\n'
        (self.app / 'login_desktop_server.py').write_text(payload + 'Path("helper-ok").touch()\n')
        (self.app / 'main.py').write_text(payload + 'import time\nfor _ in range(100):\n if Path("helper-ok").exists(): break\n time.sleep(0.02)\nassert Path("helper-ok").exists()\n')
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.app / 'helper-ok').exists())


if __name__ == '__main__':
    unittest.main()
