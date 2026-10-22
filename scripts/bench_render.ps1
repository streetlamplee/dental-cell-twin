<#
목적: 메인 Viewport 렌더 배율에 따른 벽시계 실행 시간을 잰다(같은 시드/제품 수의 짧은 run).
사용법: .\scripts\bench_render.ps1 [-Scale 0.5] [-Products 10]
인자: -Scale  메인 Viewport resolution_scale, -Products  투입 제품 수
출력: 화면(벽시계 초, 시뮬레이션 초, 배율), results/smoke/bench_runs/ 아래 run, logs/bench_render_<timestamp>.log
#>
param(
    [double]$Scale = 0.5,
    [int]$Products = 10
)
. "$PSScriptRoot\_common.ps1"
Warn-IfKitRunning

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
$exec = (Join-Path $PSScriptRoot "collect_frames.py") -replace '\\', '/'
$out = ((Join-Path $Root "results\smoke\bench_runs") -replace '\\', '/')
$s = $Scale.ToString([Globalization.CultureInfo]::InvariantCulture)
$kitArgs = "--exec `"$exec`" --/exts/visiontwin.factory/seed=42 --/exts/visiontwin.factory/maxProducts=$Products --/exts/visiontwin.factory/mainViewportScale=$s --/exts/visiontwin.factory/outputDir=`"$out`" $KitAutomationArgs"
$log = New-LogPath "bench_render"
$ErrorActionPreference = 'Continue'
$t0 = Get-Date
$sim = $null
& cmd /c "`"$bat`" $kitArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match "'simulation_time_s': ([0-9.]+)") { $sim = [double]$Matches[1] }
}
$wall = ((Get-Date) - $t0).TotalSeconds
Write-Host ("scale={0} products={1} wall={2:N1}s sim={3}s (includes app start-up)" -f $s, $Products, $wall, $sim)
