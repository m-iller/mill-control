# Сборка Windows на машине с Windows (дуалбут) и загрузка в уже созданный релиз.
# Тесты здесь локальные. Запасной путь GitHub Actions вызывает этот же скрипт
# с -SkipTests: минуты Windows-раннеров на приватных репозиториях списываются
# с коэффициентом 2, поэтому в облаке тесты не гоняются.
#
#   .\scripts\build_win.ps1 0.1.0
#   .\scripts\build_win.ps1 0.1.0 -SkipTests
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Version,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Версия должна быть вида 0.1.0"
}
$Tag = "v$Version"
git fetch --tags
git checkout $Tag

if (-not (Test-Path .venv\Scripts\python.exe)) {
    python -m venv .venv
}
.\.venv\Scripts\python -m pip install -U pip
$env:SETUPTOOLS_SCM_PRETEND_VERSION = $Version
.\.venv\Scripts\python -m pip install -e ".[dev]"

if (-not $SkipTests) {
    $env:QT_QPA_PLATFORM = "offscreen"
    .\.venv\Scripts\python -m ruff check .
    .\.venv\Scripts\python -m ruff format --check .
    .\.venv\Scripts\python -m pytest --cov --cov-report=term-missing
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (Test-Path dist) { Remove-Item -Recurse -Force dist }
if (Test-Path build) { Remove-Item -Recurse -Force build }
.\.venv\Scripts\pyinstaller --noconfirm --clean packaging\millrepair.spec
$Binary = Join-Path $Root "dist\millrepair\millrepair.exe"
if (-not (Test-Path $Binary)) {
    throw "PyInstaller не создал $Binary"
}

$SmokeDb = Join-Path ([System.IO.Path]::GetTempPath()) ("millrepair-" + [guid]::NewGuid().ToString() + ".sqlite")
& $Binary --version
if ($LASTEXITCODE -ne 0) { throw "millrepair --version завершился с кодом $LASTEXITCODE" }
& $Binary --calc --db $SmokeDb
if ($LASTEXITCODE -ne 0) { throw "millrepair --calc завершился с кодом $LASTEXITCODE" }
Remove-Item -Force $SmokeDb -ErrorAction SilentlyContinue

New-Item -ItemType Directory -Force -Path (Join-Path $Root "packaging\output") | Out-Null
$ZipName = "MillRepair-$Version-windows-x64.zip"
$ZipPath = Join-Path $Root "packaging\output\$ZipName"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path (Join-Path $Root "dist\millrepair\*") -DestinationPath $ZipPath

$SetupPath = $null
$Iscc = Get-Command ISCC -ErrorAction SilentlyContinue
if ($Iscc) {
    & $Iscc.Source (Join-Path $Root "packaging\windows\millrepair.iss") "/DVersion=$Version"
    $Candidate = Join-Path $Root "packaging\output\MillRepair-$Version-setup.exe"
    if (Test-Path $Candidate) { $SetupPath = $Candidate }
}

gh release view $Tag | Out-Null
gh release upload $Tag $ZipPath --clobber
if ($SetupPath) {
    gh release upload $Tag $SetupPath --clobber
}

$SumsPath = Join-Path $Root "packaging\output\SHA256SUMS.txt"
cmd /c "gh release download $Tag --pattern SHA256SUMS.txt --dir packaging\output --clobber"
if (-not (Test-Path $SumsPath)) { New-Item -ItemType File -Path $SumsPath | Out-Null }
$existing = Get-Content $SumsPath -ErrorAction SilentlyContinue | Where-Object {
    $_ -notmatch [regex]::Escape($ZipName) -and ($null -eq $SetupPath -or $_ -notmatch [regex]::Escape((Split-Path $SetupPath -Leaf)))
}
$lines = @($existing)
foreach ($file in @($ZipPath, $SetupPath) | Where-Object { $_ }) {
    $hash = (Get-FileHash -Algorithm SHA256 $file).Hash.ToLower()
    $lines += ("{0}  {1}" -f $hash, (Split-Path $file -Leaf))
}
Set-Content -Path $SumsPath -Value $lines -Encoding ascii
gh release upload $Tag $SumsPath --clobber
Write-Host "Windows-артефакты загружены в $Tag"
