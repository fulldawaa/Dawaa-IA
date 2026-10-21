# Construit dist\Raya-Setup.exe : tests → PyInstaller → Inno Setup.
# Usage : powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$llamaVersion = "b11718"
$llama = "vendor\llama\llama-server.exe"
if (-not (Test-Path $llama)) {
    Write-Host "Téléchargement de llama.cpp $llamaVersion (build Vulkan)…"
    $zip = Join-Path $env:TEMP "llama-$llamaVersion.zip"
    Invoke-WebRequest "https://github.com/ggml-org/llama.cpp/releases/download/$llamaVersion/llama-$llamaVersion-bin-win-vulkan-x64.zip" -OutFile $zip
    Expand-Archive $zip -DestinationPath "vendor\llama" -Force
}

Write-Host "Tests…"
& .venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Les tests ont échoué" }

Write-Host "PyInstaller…"
& .venv\Scripts\pyinstaller.exe raya.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller a échoué" }

$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 introuvable : winget install JRSoftware.InnoSetup" }

Write-Host "Inno Setup…"
& $iscc "installeur\raya.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup a échoué" }
Get-Item "dist\Raya-Setup.exe" | Select-Object Name, @{n = "Taille (Mo)"; e = { [int]($_.Length / 1MB) } }
