<#
목적: 변환된 CAD USD를 원본 URDF와 비교 검증한다(링크/부품 이름, 링크 위치, 부품 bbox, 색). (.venv-cad 필요)
사용법: .\scripts\verify_cad_usd.ps1 [-Name teeth_mill]
인자: -Name  reference\<Name>.urdf 와 assets\cad\<Name>.usd/.kinematics.json 을 사용
출력: assets/cad/<Name>.verify.json, logs/verify_cad_usd_<timestamp>.log, 실패 시 종료 코드 1
#>
param(
    [string]$Name = "teeth_mill"
)
. "$PSScriptRoot\_common.ps1"

$py = Join-Path $Root ".venv-cad\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "CAD environment missing. Run .\scripts\setup_cad_env.ps1 first." }
$urdf = Join-Path $Root "reference\$Name.urdf"
$usd = Join-Path $Root "assets\cad\$Name.usd"
$kin = Join-Path $Root "assets\cad\$Name.kinematics.json"

$log = New-LogPath "verify_cad_usd"
$ErrorActionPreference = 'Continue'
& $py (Join-Path $PSScriptRoot "verify_cad_usd.py") $urdf $usd $kin 2>&1 | ForEach-Object {
    $_; Add-Content -Path $log -Value $_ -Encoding utf8
}
exit $LASTEXITCODE
