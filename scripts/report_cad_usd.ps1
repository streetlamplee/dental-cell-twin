<#
목적: 변환된 CAD USD의 품질 리포트. USD 메시 통계(메시/삼각형/재질/메타데이터)와 원본 STEP B-rep 대비 부피·면적·크기 오차를 계산한다. (.venv-cad 필요)
사용법: .\scripts\report_cad_usd.ps1 -Usd assets\parts\usd\dental_crown.usd -Step assets\parts\raw\dental_crown.step
인자: -Usd  변환된 USD, -Step  변환에 쓴 원본 STEP
출력: <USD>.report.json, 화면 요약 한 줄, logs/report_cad_usd_<timestamp>.log
#>
param(
    [Parameter(Mandatory = $true)][string]$Usd,
    [Parameter(Mandatory = $true)][string]$Step
)
. "$PSScriptRoot\_common.ps1"

$py = Join-Path $Root ".venv-cad\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "CAD environment missing. Run .\scripts\setup_cad_env.ps1 first." }
$log = New-LogPath "report_cad_usd"
$ErrorActionPreference = 'Continue'
& $py (Join-Path $PSScriptRoot "report_cad_usd.py") (Resolve-Path $Usd).Path (Resolve-Path $Step).Path 2>&1 | ForEach-Object {
    $_; Add-Content -Path $log -Value $_ -Encoding utf8
}
exit $LASTEXITCODE
