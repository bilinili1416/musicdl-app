# Build a Windows x64 directory bundle, preserving dynamic platform modules and dictionaries.
from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata
from pathlib import Path
root = Path(SPECPATH)
datas = [(str(root / 'web'), 'web'), (str(root / 'assets' / 'musicdl.ico'), 'assets')]
binaries, hiddenimports = [], []
for package in ('musicdl', 'fugashi', 'unidic_lite', 'webview', 'nodejs_wheel'):
    package_data, package_binaries, package_imports = collect_all(package)
    datas += package_data
    binaries += package_binaries
    hiddenimports += package_imports
for package in ('musicdl', 'pywebview', 'fugashi', 'unidic-lite'):
    datas += copy_metadata(package)
datas += collect_data_files('fake_useragent')
a = Analysis([str(root / 'desktop.py')], pathex=[str(root)], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['PyQt5','PyQt6','PySide2','PySide6','cefpython3','matplotlib','pytest'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Musicdl', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root / 'assets' / 'musicdl.ico'), version=str(root / 'assets' / 'version.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Musicdl')
