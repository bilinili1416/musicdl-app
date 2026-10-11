$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$musicdlAppPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $musicdlAppPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '无法创建 Python 环境' }
}
& $musicdlAppPython -m pip install -r requirements-desktop.txt
if ($LASTEXITCODE -ne 0) { throw '运行依赖安装失败' }
& $musicdlAppPython desktop.py @args
