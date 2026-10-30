<#
목적: 실제 Kit에서 기본 crown 시작, 장애물 주입 후 Build/Start 차단, 재빌드 복구를 검증한다.
사용법: .\scripts\verify_collision_preflight.ps1
출력: results/interview/collision/<timestamp>/report.json, process.json, 로컬 실행 로그.
실패 시: failure.json, 0이 아닌 종료 코드. 기존 Kit 인스턴스가 있으면 실행하지 않는다.
#>
. "$PSScriptRoot\_interview.ps1"
$out = Join-Path $Root "results\interview\collision\$(Get-Date -Format yyyyMMdd_HHmmss)"
Invoke-InterviewKit -Script 'verify_collision_preflight.py' -Out $out -TimeoutSeconds 300 -Settings @{
    '/exts/visiontwin.factory/part'='crown'; '/exts/visiontwin.factory/vision'='false'
}
