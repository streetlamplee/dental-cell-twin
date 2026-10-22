<#
목적: GUI 앱을 실행해 컨베이어 1회 전체 실행(검사 카메라 캡처 + 실시간 판정 + 배출)을 하고 종료한다.
사용법: .\scripts\collect_frames.ps1 [-Seed 42] [-Products 30] [-Speed 0.5] [-Part box]
인자: -Seed 랜덤 시드, -Products 투입 제품 수, -Speed 컨베이어 속도(m/s),
      -Part 제품 종류(box 또는 assets/parts/catalog.json의 부품, 예: kfl08)
출력: results/runs/<timestamp>_seed<Seed>/ (frames/*.png, inspections.csv, results.csv, summary.json, run.json),
      logs/collect_frames_<timestamp>.log
#>
param(
    [int]$Seed = 42,
    [int]$Products = 30,
    [double]$Speed = 0.5,
    [string]$Part = "box"
)
. "$PSScriptRoot\_common.ps1"

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }

$exec = (Join-Path $PSScriptRoot "collect_frames.py") -replace '\\', '/'
$log = New-LogPath "collect_frames"
$speedArg = $Speed.ToString([Globalization.CultureInfo]::InvariantCulture)
$kitArgs = "--exec `"$exec`" --/exts/visiontwin.factory/seed=$Seed --/exts/visiontwin.factory/maxProducts=$Products --/exts/visiontwin.factory/speed=$speedArg --/exts/visiontwin.factory/part=$Part $KitAutomationArgs"

$ErrorActionPreference = 'Continue'
$runDir = $null
& cmd /c "`"$bat`" $kitArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match 'collect_frames\]|inspector ready|stale|id check|late\)|\[Error\]') { $_ }
    if ($_ -match 'run_dir=(.+)$') { $runDir = $Matches[1].Trim() }
}
$code = $LASTEXITCODE
if ($code -ne 0 -or -not $runDir) { Write-Host "Collect FAILED (exit $code). Log: $log"; exit 1 }
Write-Host "Collect OK: $runDir"
