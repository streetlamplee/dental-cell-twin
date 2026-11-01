<#
목적: 실제 Kit에서 새 시간표로 crown 2개를 검사하고 축 속도·복귀 중 제품 위치·출구 해제 순서를 검증한다.
사용법: .\scripts\verify_retimed_cycle.ps1
출력: results/interview/retiming/<timestamp>/report.json, process.json, 로컬 프레임/로그.
실패 시 failure.json과 0이 아닌 종료 코드. 다른 Kit가 실행 중이면 실행하지 않는다.
#>
. "$PSScriptRoot\_interview.ps1"
$out = Join-Path $Root "results\interview\retiming\$(Get-Date -Format yyyyMMdd_HHmmss)"
Invoke-InterviewKit -Script 'verify_retimed_cycle.py' -Out $out -TimeoutSeconds 600 -Settings @{
    '/exts/visiontwin.factory/part'='crown'; '/exts/visiontwin.factory/vision'='true'
    '/exts/visiontwin.factory/maxProducts'='2'; '/exts/visiontwin.factory/trace'='true'
}
