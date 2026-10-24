<#
목적: 화면 녹화용 데모 모드. GUI 앱을 열고 크라운 라인(검사 켬)을 돌리며, 셀의 단계에 맞춰 화면을 자동으로 바꾼다(전체 → 로봇 이송 근접 → 스핀들 카메라 → 전체). 끝나면 티칭 펜던트로 원점 + 5면을 재생한다. 앱은 닫히지 않는다.
사용법: .\scripts\run_demo.ps1 [-Products 4] [-Seed 42]
인자: -Products  투입 제품 수(seed 42: #2 셰이드 결함, #3 치핑), -Seed  랜덤 시드
출력: Kit 창(녹화 대상). run 기록은 results/smoke/demo_runs/, 로그는 logs/run_demo_<timestamp>.log
#>
param(
    [int]$Products = 4,
    [int]$Seed = 42
)
. "$PSScriptRoot\_common.ps1"
Warn-IfKitRunning

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }
$exec = (Join-Path $PSScriptRoot "run_demo.py") -replace '\\', '/'
$out = (Join-Path $Root "results\smoke\demo_runs") -replace '\\', '/'
$log = New-LogPath "run_demo"
$kitArgs = "--exec `"$exec`" --/visiontwin/demo/products=$Products --/visiontwin/demo/seed=$Seed --/exts/visiontwin.factory/mainViewportScale=1.0 --/exts/visiontwin.factory/outputDir=`"$out`""
Write-Host "Starting demo (the window stays open; start your screen recording when the overview appears)."
$ErrorActionPreference = 'Continue'
& cmd /c "`"$bat`" $kitArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match '\[demo\]|\[Error\]') { $_ }
}
Write-Host "Demo app closed. Log: $log"
