<#
목적: 실험 결과(results/experiments/<이름>/runs)를 분석해 조건별 표와 그래프를 만든다. 기록된 파일만 사용한다.
사용법: .\scripts\analyze_results.ps1 -Experiment day9
인자: -Experiment  experiments/<이름>.json 의 이름
출력: results/experiments/<이름>/table.csv, table.md, fig_vision.png, fig_line.png, logs/analyze_results_<timestamp>.log
#>
param(
    [Parameter(Mandatory = $true)][string]$Experiment
)
. "$PSScriptRoot\_common.ps1"

$log = New-LogPath "analyze_results"
$ErrorActionPreference = 'Continue'
& python (Join-Path $PSScriptRoot "analyze_results.py") $Experiment 2>&1 | ForEach-Object { $_; Add-Content -Path $log -Value $_ -Encoding utf8 }
exit $LASTEXITCODE
