<#
목적: 기록된 run의 events.csv와 summary.json을 점검한다(생성/종료 1회, 로딩/언로딩 짝, 검사당 판정 1회, 미종료 없음).
사용법: .\scripts\check_run.ps1 [-RunDir results\runs\<run>]
인자: -RunDir  기본값은 가장 최근 run
출력: 화면 + logs/check_run_<timestamp>.log, 문제가 있으면 종료 코드 1
#>
param(
    [string]$RunDir = ""
)
. "$PSScriptRoot\_common.ps1"

if (-not $RunDir) {
    $RunDir = (Get-ChildItem (Join-Path $Root "results\runs") -Directory | Sort-Object Name | Select-Object -Last 1).FullName
}
$log = New-LogPath "check_run"
$ErrorActionPreference = 'Continue'
& python (Join-Path $PSScriptRoot "check_run.py") $RunDir 2>&1 | ForEach-Object { $_; Add-Content -Path $log -Value $_ -Encoding utf8 }
exit $LASTEXITCODE
