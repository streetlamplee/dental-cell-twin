<#
목적: 두 run의 results.csv를 결정론적 컬럼(판정, 경로, 시뮬레이션 시간 등)으로 비교해 재현성을 확인한다.
사용법: .\scripts\compare_runs.ps1 -RunA results\runs\<a> -RunB results\runs\<b>
출력: 화면 + logs/compare_runs_<timestamp>.log, 종료 코드 0=동일 1=차이
#>
param(
    [Parameter(Mandatory = $true)][string]$RunA,
    [Parameter(Mandatory = $true)][string]$RunB
)
. "$PSScriptRoot\_common.ps1"

$log = New-LogPath "compare_runs"
$ErrorActionPreference = 'Continue'
& python (Join-Path $PSScriptRoot "compare_runs.py") $RunA $RunB 2>&1 | ForEach-Object {
    $_; Add-Content -Path $log -Value $_ -Encoding utf8
}
exit $LASTEXITCODE
