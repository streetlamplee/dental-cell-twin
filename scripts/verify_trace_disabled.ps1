<#
목적: trace CSV를 끈 비전 실행이 기존 감사 도구와 호환되는지 확인한다.
사용법: .\scripts\verify_trace_disabled.ps1
출력: results/interview/compatibility/<timestamp>/report.json 및 실행 로그.
#>
. "$PSScriptRoot\_interview.ps1"
$out = Join-Path $Root "results/interview/compatibility/$(Get-Date -Format yyyyMMdd_HHmmss)"
Invoke-InterviewKit -Script 'collect_frames.py' -Out $out -Settings @{
    '/exts/visiontwin.factory/part'='box'; '/exts/visiontwin.factory/vision'='true'
    '/exts/visiontwin.factory/seed'=42; '/exts/visiontwin.factory/maxProducts'=6
    '/exts/visiontwin.factory/speed'=0.5; '/exts/visiontwin.factory/trace'='false'
}
$run = Get-ChildItem (Join-Path $out 'runs') -Directory | Select-Object -First 1
& "$PSScriptRoot\check_run.ps1" -RunDir $run.FullName
if ($LASTEXITCODE -ne 0) { throw 'Trace-disabled legacy audit failed.' }
$summary = Get-Content (Join-Path $run.FullName 'summary.json') -Raw -Encoding utf8 | ConvertFrom-Json
if ($summary.status -ne 'complete' -or $summary.products -ne 6 -or $summary.sort_correct -ne 6) { throw 'Trace-disabled outcomes failed.' }
if (Test-Path (Join-Path $run.FullName 'trace.csv')) { throw 'Trace CSV unexpectedly written with trace=false.' }
@{passed=$true; trace_csv_exists=$false; products=6; sort_correct=6; run=$run.FullName;
    legacy_audit_passed=$true; timing_summary_present=($null -ne $summary.timing)} |
    ConvertTo-Json -Depth 4 | Set-Content (Join-Path $out 'report.json') -Encoding utf8
Write-Host "PASS: trace=false vision run, existing audit, timing summary: $out"
