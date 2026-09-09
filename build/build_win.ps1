# Windows 빌드 스크립트. 프로젝트 루트에서 실행:
#   powershell -ExecutionPolicy Bypass -File build\build_win.ps1            (폴더 형태)
#   powershell -ExecutionPolicy Bypass -File build\build_win.ps1 -OneFile   (단일 exe)
param(
    [switch]$OneFile,
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

& $py -m pip install --quiet -r requirements.txt pyinstaller

$env:MCW_ONEFILE = if ($OneFile) { "1" } else { "0" }
$env:MCW_VERSION = $Version

& $py -m PyInstaller --noconfirm --clean --distpath dist --workpath build\work build\build.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$suffix = if ($OneFile) { "onefile" } else { "onedir" }
$zip = "dist\MyChatGPTWeb-$Version-windows-x64-$suffix.zip"
if (Test-Path $zip) { Remove-Item $zip }
if ($OneFile) {
    Compress-Archive -Path "dist\MyChatGPTWeb.exe" -DestinationPath $zip
} else {
    Compress-Archive -Path "dist\MyChatGPTWeb" -DestinationPath $zip
}
Write-Host "Built: $zip"
