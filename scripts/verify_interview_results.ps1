<#
목적: 기록된 면접 실험의 반복 횟수·타임아웃 사유·결과·회귀 비교를 최종 감사.
사용법: .\scripts\verify_interview_results.ps1
출력: results/interview/verification.json, logs/verify_interview_results_*.log. 누락·불일치는 실패.
#>
. "$PSScriptRoot\_common.ps1"
$log = New-LogPath 'verify_interview_results'
$ErrorActionPreference = 'Continue'
& python "$PSScriptRoot\verify_interview_results.py" 2>&1 | ForEach-Object { $_; Add-Content $log $_ -Encoding utf8 }
if ($LASTEXITCODE -ne 0) { throw "Recorded experiment verification failed: $log" }
