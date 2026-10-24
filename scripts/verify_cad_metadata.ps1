<#
목적: CAD(STEP) → USD 변환에서 메타데이터가 보존되는지 확인한다. STEP 어셈블리의 제품/부품 이름(OpenCascade)과 USD의 omni:hoops:metadata 속성을 자산별로 대조한다. (.venv-cad 필요)
사용법: .\scripts\verify_cad_metadata.ps1
출력: results/cad_metadata/report.json, report.md, 화면 요약, logs/verify_cad_metadata_<timestamp>.log (누락이 있으면 종료 코드 1)
#>
. "$PSScriptRoot\_common.ps1"

$py = Join-Path $Root ".venv-cad\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "CAD environment missing. Run .\scripts\setup_cad_env.ps1 first." }
$log = New-LogPath "verify_cad_metadata"
$ErrorActionPreference = 'Continue'
& $py (Join-Path $PSScriptRoot "verify_cad_metadata.py") 2>&1 | ForEach-Object {
    $_; Add-Content -Path $log -Value $_ -Encoding utf8
}
exit $LASTEXITCODE
