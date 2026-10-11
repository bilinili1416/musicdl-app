import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import desktop_runtime as runtime

class DesktopTests(unittest.TestCase):
    def test_portable_and_installed_directories_do_not_use_web_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(runtime, 'application_directory', return_value=root), patch.dict(runtime.os.environ, {'LOCALAPPDATA': str(root / 'local')}):
                self.assertEqual(runtime.data_directory(), root / 'local' / 'MusicdlApp')
                (root / 'portable.flag').write_text('portable')
                self.assertEqual(runtime.data_directory(), root / 'data')
                self.assertEqual(runtime.data_directory(root / 'custom'), (root / 'custom').resolve())

    def test_preferences_are_atomic_unicode_and_restricted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state' / 'preferences.json'
            values = {'musicdl.searchHistory': json.dumps(['青のすみか'], ensure_ascii=False)}
            runtime.save_json(path, runtime.validate_preferences(values))
            self.assertEqual(runtime.read_json(path, {}), values)
            self.assertEqual(list(path.parent.glob('*.tmp')), [])
            for bad in [[], {'secret': 'not a musicdl key'}, {'musicdl.preferences': {}}, {'musicdl.history': 'a' * (runtime.MAX_PREFERENCES + 1)}]:
                with self.assertRaises(ValueError):
                    runtime.validate_preferences(bad)

    def test_single_instance_lock_releases_cleanly(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'application.lock'
            first, second = runtime.InstanceLock(path), runtime.InstanceLock(path)
            first.acquire()
            try:
                with self.assertRaises(RuntimeError):
                    second.acquire()
            finally:
                first.close()
            second.acquire()
            second.close()


class DesktopServiceTests(unittest.TestCase):
    def test_service_restart_port_conflict_preferences_and_shutdown(self):
        import socket
        import urllib.request
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            first = runtime.DesktopService(data)
            try:
                first.start()
                self.assertEqual(first.request('/api/status')['deployment'], 'desktop')
                self.assertEqual(first.request('/api/desktop/info')['dataDirectory'], str(data))
                concurrent = runtime.DesktopService(data / 'concurrent')
                try:
                    concurrent.start()
                    self.assertNotEqual(concurrent.url, first.url)
                    self.assertEqual(concurrent.request('/api/desktop/info')['dataDirectory'], str(data / 'concurrent'))
                finally:
                    concurrent.stop()
                preferences = {'musicdl.playback': '{"lastFile":null}', 'musicdl.searchHistory': '["日本語"]'}
                self.assertTrue(first.request('/api/desktop/preferences', preferences)['ok'])
                port = int(first.url.rsplit(':', 1)[1])
                url = first.url
            finally:
                first.stop()
            self.assertEqual(runtime.read_json(data / '.musicdl-app' / 'preferences.json', {}), preferences)
            with self.assertRaises(OSError):
                urllib.request.urlopen(url + '/api/status', timeout=1)
            blocker = socket.socket()
            blocker.bind(('127.0.0.1', port))
            blocker.listen()
            second = runtime.DesktopService(data)
            try:
                second.start()
                self.assertNotEqual(second.url, url)
                with urllib.request.urlopen(second.url + '/desktop-state.js', timeout=5) as response:
                    bootstrap = response.read().decode()
                self.assertEqual(json.loads(bootstrap.split('=', 1)[1].rstrip(';')), preferences)
                self.assertEqual(second.request('/api/library')['songs'], [])
            finally:
                second.stop()
                blocker.close()
