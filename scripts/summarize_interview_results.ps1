<#
목적: 면접 준비 실험의 원시 결과를 비교표로 집계한다.
사용법: .\scripts\summarize_interview_results.ps1
출력: results/interview/report.md, report.json, logs/summarize_interview_results_*.log
#>
. "$PSScriptRoot\_common.ps1"
$log = New-LogPath 'summarize_interview_results'
& python "$PSScriptRoot\summarize_interview_results.py" 2>&1 | ForEach-Object { $_; Add-Content $log $_ -Encoding utf8 }
if ($LASTEXITCODE -ne 0) { throw "Summary failed: $log" }
