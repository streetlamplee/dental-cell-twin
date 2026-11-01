<#
목적: 현재 로봇 이송/검사 기계 궤적의 관절 속도·가속도 최대값과 URDF 제한을 비교한다.
사용법: .\scripts\check_joint_rates.ps1 [-Out <새 결과 폴더>]
환경: 시스템 Python + numpy. 로봇 원본 URDF는 fetch_robot.ps1로 준비한다. Kit/GPU 불필요.
출력: results/joint_rates/<timestamp>/report.json, report.md. 런타임 시간표는 바꾸지 않는다.
종료: 0 전체 확인/제한 이내, 2 알려진 제한 초과/위치 불연속, 3 제한 누락으로 검증 미완료, 1 실행 오류.
#>
param([string]$Out = "")
. "$PSScriptRoot\_common.ps1"
$arguments = @((Join-Path $PSScriptRoot "check_joint_rates.py"))
if ($Out) { $arguments += @("--out", $Out) }
& python @arguments
exit $LASTEXITCODE
