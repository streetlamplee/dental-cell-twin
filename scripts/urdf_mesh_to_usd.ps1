<#
목적: 메시(STL) 시각 요소를 가진 URDF(예: Seeed reBot Arm)를 USD + kinematics.json으로 바꾼다. 관절은 kinematics.json으로 보존하고 Kit에서 FK로 구동한다. (.venv-cad 필요)
사용법: .\scripts\urdf_mesh_to_usd.ps1 -Urdf <file.urdf> -Out <file.usd>
인자: -Urdf  입력 URDF(메시 경로는 URDF 기준 상대 경로), -Out  출력 USD
출력: USD, <Out>.kinematics.json, logs/urdf_mesh_to_usd_<timestamp>.log
#>
param(
    [Parameter(Mandatory = $true)][string]$Urdf,
    [Parameter(Mandatory = $true)][string]$Out
)
. "$PSScriptRoot\_common.ps1"

$py = Join-Path $Root ".venv-cad\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "CAD environment missing. Run .\scripts\setup_cad_env.ps1 first." }
$log = New-LogPath "urdf_mesh_to_usd"
$outFull = [IO.Path]::GetFullPath((Join-Path (Get-Location) $Out))
New-Item -ItemType Directory -Force -Path (Split-Path $outFull) | Out-Null
$ErrorActionPreference = 'Continue'
& $py (Join-Path $PSScriptRoot "urdf_mesh_to_usd.py") (Resolve-Path $Urdf).Path $outFull 2>&1 | ForEach-Object {
    $_; Add-Content -Path $log -Value $_ -Encoding utf8
}
exit $LASTEXITCODE
