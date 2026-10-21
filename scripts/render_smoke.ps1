<#
목적: GUI 앱을 실행해 팩토리 씬을 만들고 컨베이어를 잠시 돌린 뒤 Viewport를 PNG로 저장하고 종료한다.
      사람이 화면을 보지 않고도 "씬이 실제로 렌더되는지" 확인하기 위한 스모크 테스트.
사용법: .\scripts\render_smoke.ps1 [-Frames 240]
인자: -Frames  캡처 전 컨베이어를 돌릴 업데이트 프레임 수
출력: results/smoke/render_smoke_<timestamp>.png, logs/render_smoke_<timestamp>.log
#>
param(
    [int]$Frames = 240
)
. "$PSScriptRoot\_common.ps1"

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }

$outDir = Join-Path $Root "results\smoke"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$png = (Join-Path $outDir "render_smoke_$stamp.png") -replace '\\', '/'
$exec = (Join-Path $PSScriptRoot "render_smoke.py") -replace '\\', '/'
$log = New-LogPath "render_smoke"

$kitArgs = "--exec `"$exec`" --/visiontwin/smoke/out=`"$png`" --/visiontwin/smoke/frames=$Frames $KitAutomationArgs"
$ErrorActionPreference = 'Continue'
& cmd /c "`"$bat`" $kitArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match 'render_smoke|\[Error\]') { $_ }
}
$code = $LASTEXITCODE
if ($code -ne 0 -or -not (Test-Path $png)) { Write-Host "Render smoke FAILED (exit $code). Log: $log"; exit 1 }
Write-Host "Render smoke OK: $png"
