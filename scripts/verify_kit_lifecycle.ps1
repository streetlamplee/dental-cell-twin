<#
목적: 실제 Kit에서 구세대 콜백과 pending 캡처를 Reset·Stage 교체·확장 종료로 무효화하는지 검증.
사용법: .\scripts\verify_kit_lifecycle.ps1 [-Before] [-Repeats 10]
출력: results/interview/lifecycle/<before|after>_<timestamp>/report.json 및 단계별 run.
#>
param([switch]$Before, [int]$Repeats = 10)
. "$PSScriptRoot\_interview.ps1"
$label = if ($Before) { 'before' } else { 'after' }
$out = Join-Path $Root "results\interview\lifecycle\${label}_$(Get-Date -Format yyyyMMdd_HHmmss)"
$snapshot = Get-ChildItem (Join-Path $Root 'results\interview\source_before') -Directory | Sort-Object Name -Descending | Select-Object -First 1
Invoke-InterviewKit -Script 'verify_kit_lifecycle.py' -Out $out -TimeoutSeconds 900 -Settings @{
    '/exts/visiontwin.factory/part'='box'; '/exts/visiontwin.factory/vision'='true'
    '/exts/visiontwin.factory/trace'='true'; '/visiontwin/interview/repeats'=$Repeats
    '/visiontwin/interview/before'=$Before.IsPresent.ToString().ToLowerInvariant()
    '/visiontwin/interview/beforeSource'=$snapshot.FullName
}
