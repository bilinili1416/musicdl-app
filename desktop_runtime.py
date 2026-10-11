"""Windows desktop lifecycle and persistent storage, independent of Musicdl Web."""
from __future__ import annotations
import ctypes
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

APP_NAME = 'Musicdl App'
APP_VERSION = '0.1.0'
ROOT = Path(__file__).resolve().parent
MAX_PREFERENCES = 2 * 1024 * 1024


def application_directory():
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else ROOT


def data_directory(explicit=None):
    if explicit:
        return Path(explicit).expanduser().resolve()
    base = application_directory()
    if (base / 'portable.flag').is_file():
        return base / 'data'
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'MusicdlApp'


def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return fallback


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def validate_preferences(values):
    if not isinstance(values, dict) or len(values) > 100:
        raise ValueError('无效的桌面偏好')
    if any(not isinstance(k, str) or not k.startswith('musicdl.') or len(k) > 100
           or not isinstance(v, str) for k, v in values.items()):
        raise ValueError('无效的桌面偏好')
    if len(json.dumps(values).encode('utf-8')) > MAX_PREFERENCES:
        raise ValueError('桌面记录过大')
    return values


class InstanceLock:
    def __init__(self, path):
        self.path, self.stream = path, None

    def acquire(self):
        import msvcrt
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('a+b')
        if self.path.stat().st_size == 0:
            self.stream.write(b'\0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.stream.close()
            self.stream = None
            raise RuntimeError('此数据目录的 Musicdl App 已在运行，请回到已打开的窗口。')

    def close(self):
        if self.stream:
            import msvcrt
            self.stream.seek(0)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            self.stream.close()
            self.stream = None


class WindowsJob:
    """Kill only our backend and its descendants if the app exits or crashes."""
    def __init__(self, process):
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                        ('flags', wintypes.DWORD), ('min_working', ctypes.c_size_t),
                        ('max_working', ctypes.c_size_t), ('active', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                        ('scheduling', wintypes.DWORD)]
        class Counters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', Counters), ('process_memory', ctypes.c_size_t),
                        ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t),
                        ('peak_job', ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def package_probe(pipe):
    """Runs in a real spawn worker, including when launched from the frozen EXE."""
    try:
        import server
        import songtools
        from nodejs_wheel import executable
        clients = [type(server.build_client(source, 1).music_clients[source]).__name__ for source in server.SOURCES]
        tokens = songtools.ruby_tokens('君の声')
        pipe.send(({'clients': clients, 'ruby': tokens, 'node': (Path(executable.ROOT_DIR) / 'node.exe').is_file()}, None))
    except Exception as exc:
        pipe.send((None, str(exc)))
    finally:
        pipe.close()


def run_backend(data, port, ready_file, shutdown_token, diagnostics=False):
    os.environ['MUSICDL_DATA_DIR'] = str(data)
    import server
    pref_path = data / '.musicdl-app' / 'preferences.json'
    pref_lock = threading.RLock()
    values = read_json(pref_path, {})
    values = validate_preferences(values)

    class DesktopHandler(server.Handler):
        def do_GET(self):
            path = self.path.split('?', 1)[0]
            if path == '/desktop-state.js':
                if not self.check_access():
                    return
                with pref_lock:
                    payload = json.dumps(values, ensure_ascii=True).replace('<', r'\u003c')
                body = ('window.MusicdlDesktopInitial=' + payload + ';').encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/javascript; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                self.wfile.write(body)
                return
            if path == '/desktop.js':
                if self.check_access():
                    self.serve_file(ROOT / 'web' / 'desktop.js')
                return
            if path == '/api/desktop/info':
                if self.check_access():
                    self.json_response({'name': APP_NAME, 'version': APP_VERSION, 'dataDirectory': str(data)})
                return
            if path == '/api/desktop/diagnostics' and diagnostics:
                if not self.check_access():
                    return
                probe, error = server.isolated_call(package_probe, (), 25)
                return self.json_response({'probe': probe, 'error': error})
            if path == '/api/status':
                if not self.check_access():
                    return
                import importlib.metadata
                try:
                    version = importlib.metadata.version('musicdl')
                except importlib.metadata.PackageNotFoundError:
                    version = None
                return self.json_response({'ready': bool(version), 'version': version, 'deployment': 'desktop',
                    'sources': [{'id': k, **v} for k, v in server.SOURCES.items()], 'output': str(server.OUTPUT)})
            return super().do_GET()

        def do_POST(self):
            path = self.path.split('?', 1)[0]
            if path not in {'/api/desktop/preferences', '/api/desktop/quit'}:
                return super().do_POST()
            if not self.check_access():
                return
            if path == '/api/desktop/quit':
                if not secrets.compare_digest(self.headers.get('X-Desktop-Token', ''), shutdown_token):
                    return self.json_response({'error': '不允许此请求'}, 403)
                self.json_response({'ok': True})
                threading.Thread(target=http.shutdown, daemon=True).start()
                return
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= MAX_PREFERENCES:
                    self.close_connection = True
                    return self.json_response({'error': '桌面记录过大'}, 413)
                updated = validate_preferences(json.loads(self.rfile.read(length)))
                with pref_lock:
                    save_json(pref_path, updated)
                    values.clear()
                    values.update(updated)
                self.json_response({'ok': True})
            except (ValueError, TypeError) as exc:
                self.json_response({'error': str(exc)}, 400)
            except OSError:
                self.json_response({'error': '无法保存桌面记录，请检查数据目录权限'}, 500)

    server.OUTPUT.mkdir(parents=True, exist_ok=True)
    server.load_jobs()
    server.load_imports()
    class ExclusiveHTTPServer(server.ThreadingHTTPServer):
        allow_reuse_address = False

        def server_bind(self):
            # SO_REUSEADDR can route requests to a different Windows listener.
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

    try:
        http = ExclusiveHTTPServer(('127.0.0.1', port), DesktopHandler)
    except OSError:
        http = ExclusiveHTTPServer(('127.0.0.1', 0), DesktopHandler)
    save_json(ready_file, {'port': http.server_port, 'pid': os.getpid()})
    try:
        http.serve_forever()
    finally:
        http.server_close()
        for pool in (server.SEARCH_POOL, server.DOWNLOAD_POOL, server.IMPORT_POOL):
            pool.shutdown(wait=False, cancel_futures=True)


class DesktopService:
    def __init__(self, data, diagnostics=False):
        self.data, self.diagnostics = Path(data), diagnostics
        self.process = self.job = self.log = None
        self.url = ''
        self.token = secrets.token_urlsafe(32)
        self.ready_file = self.data / '.musicdl-app' / ('backend-' + uuid.uuid4().hex + '.json')

    def start(self):
        state = self.data / '.musicdl-app'
        state.mkdir(parents=True, exist_ok=True)
        settings = read_json(state / 'settings.json', {})
        port = settings.get('port', 18765) if isinstance(settings, dict) else 18765
        if not isinstance(port, int) or not 1024 <= port <= 65535:
            port = 18765
        prefix = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(ROOT / 'desktop.py')]
        command = prefix + ['--backend', '--data-dir', str(self.data), '--port', str(port),
                            '--ready-file', str(self.ready_file), '--shutdown-token', self.token]
        if self.diagnostics:
            command.append('--diagnostics')
        env = dict(os.environ)
        for name in ('MUSICDL_PASSWORD', 'MUSICDL_USERNAME', 'MUSICDL_PUBLIC_ORIGIN', 'RAILWAY_PUBLIC_DOMAIN', 'HOST', 'PORT'):
            env.pop(name, None)
        env.update(MUSICDL_DATA_DIR=str(self.data), PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
        self.log = (state / 'app.log').open('ab')
        self.process = subprocess.Popen(command, env=env, cwd=application_directory(),
                                        stdout=self.log, stderr=self.log, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.job = WindowsJob(self.process)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError('音乐服务启动失败，请查看数据目录中 .musicdl-app/app.log。')
                if self.ready_file.exists():
                    info = read_json(self.ready_file, {})
                    if isinstance(info.get('pid'), int) and info['pid'] > 0 and isinstance(info.get('port'), int):
                        self.url = 'http://127.0.0.1:' + str(info['port'])
                        save_json(state / 'settings.json', {'port': info['port']})
                        return self.url
                time.sleep(.1)
            raise RuntimeError('音乐服务启动超时，请查看 .musicdl-app/app.log。')
        except Exception:
            self.stop()
            raise

    def request(self, path, body=None):
        request = urllib.request.Request(self.url + path, data=json.dumps(body).encode() if body is not None else None,
                                         headers={'Content-Type': 'application/json', 'X-Desktop-Token': self.token})
        with urllib.request.urlopen(request, timeout=35) as response:
            return json.loads(response.read())

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                self.request('/api/desktop/quit', {})
                self.process.wait(timeout=3)
            except Exception:
                pass
        if self.job:
            self.job.close()
            self.job = None
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)
        if self.log:
            self.log.close()
            self.log = None
        self.ready_file.unlink(missing_ok=True)
