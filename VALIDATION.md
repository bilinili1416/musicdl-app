# Validation — Musicdl App 0.1.0

Validated on Windows 11 x64, Python 3.12.15, 2026-10-11.

- 39 Python tests passed: copied backend tests and desktop storage, locking, startup, shutdown, concurrent instances and occupied-port recovery.
- 7 Node tests passed: search history, resume and playlist ordering.
- JavaScript syntax checks passed for app.js and desktop.js.
- Browser preview loaded the desktop interface and preserved the selected search mode after reload.
- Frozen Musicdl.exe --self-test exited with code 0. Checked six musicdl clients in a real spawn worker, Japanese readings, bundled Node.js and Windows GUI module imports.
- Desktop data used separate test directories; original Musicdl Web music and preferences were not imported or changed.

The native WebView2 window, Windows file chooser, real platform network requests and audio-format playback still need user testing. Automated diagnostics do not cover those interactions.
