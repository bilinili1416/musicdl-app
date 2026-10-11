"""Launch the standalone Musicdl App; multiprocessing must initialize before GUI imports."""
import multiprocessing as mp
import sys
import os

# Windowed executables and spawn workers have no console streams.
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

if __name__ == '__main__':
    mp.freeze_support()

import argparse
import ctypes
import json
from pathlib import Path
import traceback

from desktop_runtime import APP_NAME, APP_VERSION, ROOT, DesktopService, InstanceLock, data_directory, run_backend, validate_preferences


def message(text, warning=False):
    return ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x30 if warning else 0x10)


def main():
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument('--data-dir')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--backend', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--port', type=int, default=18765, help=argparse.SUPPRESS)
    parser.add_argument('--ready-file', help=argparse.SUPPRESS)
    parser.add_argument('--shutdown-token', help=argparse.SUPPRESS)
    parser.add_argument('--diagnostics', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    data = data_directory(args.data_dir)
    if args.backend:
        log = data / '.musicdl-app' / 'app.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = log.open('a', encoding='utf-8', buffering=1)
        run_backend(data, args.port, Path(args.ready_file), args.shutdown_token, args.diagnostics)
        return
    lock = InstanceLock(data / '.musicdl-app' / 'application.lock')
    service = DesktopService(data, diagnostics=args.self_test)
    try:
        lock.acquire()
        service.start()
        if args.self_test:
            status = service.request('/api/status')
            info = service.request('/api/desktop/info')
            diagnosis = service.request('/api/desktop/diagnostics')
            import webview
            import webview.platforms.winforms
            if not status['ready'] or diagnosis.get('error') or diagnosis.get('probe', {}).get('error'):
                raise RuntimeError(str(diagnosis))
            probe = diagnosis['probe']
            if len(probe['clients']) != 6 or not probe['node'] or not any(t['reading'] for t in probe['ruby']):
                raise RuntimeError('打包资源检查失败：' + str(probe))
            report = {'ok': True, 'version': APP_VERSION, 'status': status, 'info': info,
                      'diagnostics': diagnosis, 'webview': webview.__version__ if hasattr(webview, '__version__') else 'imported'}
            (data / '.musicdl-app' / 'self-test.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(report, ensure_ascii=False))
            return
        import webview
        webview.settings['ALLOW_DOWNLOADS'] = True
        webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True
        webview.settings['ALLOW_FILE_URLS'] = False

        class DesktopAPI:
            def open_data_directory(self):
                os.startfile(str(data))
                return True

        window = webview.create_window(APP_NAME, service.url, js_api=DesktopAPI(), width=1180, height=820,
                                       min_size=(760, 560), text_select=True, background_color='#faf9fc')

        def closing():
            try:
                jobs = service.request('/api/downloads')['jobs']
                imports = service.request('/api/imports')['imports']
                active = any(j['status'] in {'queued', 'resolving', 'downloading'} for j in jobs) or any(j['status'] == 'checking' for j in imports)
                if active:
                    answer = ctypes.windll.user32.MessageBoxW(None, '还有下载或歌词补全任务正在进行。关闭应用会中断这些任务，确定关闭？', APP_NAME, 0x34)
                    if answer != 6:
                        return False
                values = window.evaluate_js("window.dispatchEvent(new Event('musicdl-closing')); window.MusicdlDesktopStorage ? window.MusicdlDesktopStorage.snapshot() : null")
                if isinstance(values, dict):
                    service.request('/api/desktop/preferences', validate_preferences(values))
            except Exception:
                with (data / '.musicdl-app' / 'app.log').open('a', encoding='utf-8') as stream:
                    stream.write(traceback.format_exc())
            return True

        window.events.closing += closing
        webview.start(gui='edgechromium', private_mode=False, storage_path=str(data / '.musicdl-app' / 'browser'))
    finally:
        service.stop()
        lock.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        detail = traceback.format_exc()
        try:
            explicit = sys.argv[sys.argv.index('--data-dir') + 1] if '--data-dir' in sys.argv else None
            failure_dir = data_directory(explicit) / '.musicdl-app'
            failure_dir.mkdir(parents=True, exist_ok=True)
            with (failure_dir / 'app.log').open('a', encoding='utf-8') as stream:
                stream.write(detail)
            if '--self-test' in sys.argv:
                (failure_dir / 'self-test.json').write_text(json.dumps({'ok': False, 'error': str(exc), 'traceback': detail}, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass
        if '--backend' in sys.argv or '--self-test' in sys.argv:
            traceback.print_exc()
        else:
            message(str(exc) + '\n\n请检查数据目录是否可写，以及是否已安装 Microsoft Edge WebView2 运行时。\n官方安装页面：https://developer.microsoft.com/microsoft-edge/webview2/')
        sys.exit(1)
