<#
목적: URDF를 STEP 어셈블리(링크별 부품, mm)와 관절 정보 kinematics.json으로 변환한다. (.venv-cad 필요)
사용법: .\scripts\urdf_to_step.ps1 [-Urdf reference\teeth_mill.urdf]
인자: -Urdf  입력 URDF (기본: reference\teeth_mill.urdf)
출력: assets/cad/<이름>.stp, assets/cad/<이름>.kinematics.json, logs/urdf_to_step_<timestamp>.log
#>
param(
    [string]$Urdf = "reference\teeth_mill.urdf"
)
. "$PSScriptRoot\_common.ps1"

$py = Join-Path $Root ".venv-cad\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "CAD environment missing. Run .\scripts\setup_cad_env.ps1 first." }
$src = Resolve-Path (Join-Path $Root $Urdf)
$out = Join-Path $Root ("assets\cad\" + [IO.Path]::GetFileNameWithoutExtension($Urdf) + ".stp")

$log = New-LogPath "urdf_to_step"
$ErrorActionPreference = 'Continue'
& $py (Join-Path $PSScriptRoot "urdf_to_step.py") $src $out 2>&1 | ForEach-Object {
    if ($_ -notmatch 'cannot open font') { $_ }
    Add-Content -Path $log -Value $_ -Encoding utf8
}
exit $LASTEXITCODE
