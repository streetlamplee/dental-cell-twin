<#
목적: 최근 before/after 30개 기준 실행의 결정론적 결과를 제품별로 비교.
사용법: .\scripts\compare_interview_baselines.ps1
출력: logs/compare_runs_*.log, results/interview/baseline/comparison.json. 차이 시 실패.
#>
. "$PSScriptRoot\_common.ps1"
$base = Join-Path $Root 'results\interview\baseline'
$before = Get-ChildItem $base -Directory -Filter 'before_*' | Where-Object { Test-Path (Join-Path $_.FullName 'crown_2\process.json') } | Sort-Object Name -Descending | Select-Object -First 1
$after = Get-ChildItem $base -Directory -Filter 'after_*' | Where-Object { Test-Path (Join-Path $_.FullName 'crown_2\process.json') } | Sort-Object Name -Descending | Select-Object -First 1
if (-not $before -or -not $after) { throw 'Complete before and after baselines are required.' }
$rows = @()
foreach ($part in @('box','crown')) {
    foreach ($repeat in 1..2) {
        $a = Get-ChildItem (Join-Path $before.FullName "${part}_$repeat\runs") -Directory | Select-Object -First 1
        $b = Get-ChildItem (Join-Path $after.FullName "${part}_$repeat\runs") -Directory | Select-Object -First 1
        & "$PSScriptRoot\compare_runs.ps1" -RunA $a.FullName -RunB $b.FullName
        $same = $LASTEXITCODE -eq 0
        $rows += @{part=$part; repeat=$repeat; before=$a.FullName; after=$b.FullName; identical=$same}
    }
}
$rows | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $base 'comparison.json') -Encoding utf8
if (@($rows | Where-Object { -not $_.identical }).Count) { throw 'Before/after differences recorded in baseline/comparison.json.' }
Write-Host 'PASS: all four before/after deterministic comparisons identical.'
