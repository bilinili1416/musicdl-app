param([switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$musicdlAppPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $musicdlAppPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '无法创建 Python 环境' }
}
if (-not $SkipInstall) {
    & $musicdlAppPython -m pip install -r requirements-desktop.txt -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw '依赖安装失败' }
}
$musicdlAppDist = Join-Path $PSScriptRoot 'dist\Musicdl'
if (Test-Path -LiteralPath (Join-Path $musicdlAppDist 'data')) {
    throw '打包目录存在用户 data 数据，请先将它备份并移出 dist/Musicdl 后再打包。'
}
& $musicdlAppPython -m PyInstaller --noconfirm musicdl-app.spec
if ($LASTEXITCODE -ne 0) { throw 'Windows 打包失败' }
$musicdlAppDist = Join-Path $PSScriptRoot 'dist\Musicdl'
[IO.File]::WriteAllText((Join-Path $musicdlAppDist 'portable.flag'), 'Portable data is saved beside Musicdl.exe in data.')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'PORTABLE-README.txt') -Destination $musicdlAppDist
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'THIRD-PARTY-NOTICES.md') -Destination $musicdlAppDist
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'licenses') -Destination $musicdlAppDist -Recurse -Force
$musicdlAppArchive = Join-Path $PSScriptRoot 'dist\Musicdl-App-0.1.0-win-x64.zip'
Compress-Archive -LiteralPath $musicdlAppDist -DestinationPath $musicdlAppArchive -Force
Write-Output ('Portable application: ' + $musicdlAppDist)
Write-Output ('Archive: ' + $musicdlAppArchive)
