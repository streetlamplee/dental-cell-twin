<#
목적: 실제 native 예약 캡처를 네 수명주기 전환에서 각 10회 취소·정리 검증.
사용법: .\scripts\verify_pending_lifecycle.ps1
출력: results/interview/lifecycle_pending/<timestamp>/report.json. readback 진행 상태도 기록.
#>
. "$PSScriptRoot\_interview.ps1"
$out = Join-Path $Root "results\interview\lifecycle_pending\$(Get-Date -Format yyyyMMdd_HHmmss)"
Invoke-InterviewKit -Script 'verify_pending_lifecycle.py' -Out $out -TimeoutSeconds 900 -Settings @{
    '/exts/visiontwin.factory/part'='box'; '/exts/visiontwin.factory/vision'='true'
    '/exts/visiontwin.factory/outputDir'=$out; '/exts/visiontwin.factory/trace'='true'
}
