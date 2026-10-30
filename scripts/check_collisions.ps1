<#
목적: Kit/GPU 없이 실제 USD 형상과 이송 궤적의 보수적인 충돌 사전 검사를 실행한다.
사용법: .\scripts\check_collisions.ps1 [-Out <새 결과 폴더>] [-MaxDt 0.008333333333] [-MarginMm 0]
환경: .venv-cad (scripts/setup_cad_env.ps1), 기계 및 로봇 USD 자산.
출력: results/collision/<timestamp>/report.json, report.md.
종료 코드: 0 샘플에서 간섭 없음, 2 잠재 간섭 발견, 1 실행 오류. 연속 충돌 안전 보장은 아님.
#>
param(
    [string]$Out = "",
    [double]$MaxDt = 0.008333333333333333,
    [double]$MaxAngleDeg = 1.0,
    [double]$MarginMm = 0.0
)
. "$PSScriptRoot\_common.ps1"
$cadPython = Join-Path $Root ".venv-cad\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $cadPython)) { throw "Run scripts/setup_cad_env.ps1 first" }
$arguments = @((Join-Path $PSScriptRoot "check_collisions.py"), "--max-dt", $MaxDt.ToString("R", [cultureinfo]::InvariantCulture),
               "--max-angle-deg", $MaxAngleDeg.ToString("R", [cultureinfo]::InvariantCulture),
               "--margin-mm", $MarginMm.ToString("R", [cultureinfo]::InvariantCulture))
if ($Out) { $arguments += @("--out", $Out) }
& $cadPython @arguments
exit $LASTEXITCODE
