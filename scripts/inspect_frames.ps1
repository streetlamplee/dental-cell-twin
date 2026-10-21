<#
목적: 저장된 run의 프레임을 Kit 없이 다시 검사해 예측 CSV, 지표, 오검출 프레임을 만든다.
사용법: .\scripts\inspect_frames.ps1 [-RunDir results\runs\<run>] [-Config config\inspector.json]
인자: -RunDir  기본값은 가장 최근 run, -Config  보정된 검사기 설정(없으면 run.json 설정 사용)
출력: <run>/offline/predictions.csv, <run>/offline/errors/*.png, logs/inspect_frames_<timestamp>.log
#>
param(
    [string]$RunDir = "",
    [string]$Config = ""
)
. "$PSScriptRoot\_common.ps1"

if (-not $RunDir) {
    $latest = Get-ChildItem (Join-Path $Root "results\runs") -Directory | Sort-Object Name | Select-Object -Last 1
    if (-not $latest) { throw "No runs in results\runs. Run .\scripts\collect_frames.ps1 first." }
    $RunDir = $latest.FullName
}
$pyArgs = @((Join-Path $PSScriptRoot "inspect_frames.py"), $RunDir)
if ($Config) { $pyArgs += @("--config", $Config) }

$log = New-LogPath "inspect_frames"
$ErrorActionPreference = 'Continue'
& python @pyArgs 2>&1 | ForEach-Object { $_; Add-Content -Path $log -Value $_ -Encoding utf8 }
exit $LASTEXITCODE
