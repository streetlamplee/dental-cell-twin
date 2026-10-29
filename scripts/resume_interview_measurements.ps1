<#
목적: PC 종료로 남긴 고도화 검증만 재개. 완료한 시간 21회·인스턴싱 렌더 27회는 재실행하지 않음.
사용법: .\scripts\resume_interview_measurements.ps1 [-BaselineDirectory <중단 배치>]
출력: 새 after 기준 실행, native pending 40회, LOD 9회, 최종 검사 및 results/interview/verification.json.
#>
param([string]$BaselineDirectory = '')
. "$PSScriptRoot\_common.ps1"
if (Get-Process kit -ErrorAction SilentlyContinue) { throw 'Close the existing Kit before resuming.' }
$steps = @(
    @{name='baseline'; args=@{Label='after'; Products=30; BatchDirectory=$BaselineDirectory}; script='run_interview_baseline.ps1'},
    @{name='baseline_comparison'; script='compare_interview_baselines.ps1'},
    @{name='capture_duplicate_audit'; script='diagnose_capture_duplicates.ps1'},
    @{name='native_pending'; script='verify_pending_lifecycle.ps1'},
    @{name='lod'; script='benchmark_interview_lod.ps1'},
    @{name='core_tests'; script='test_core.ps1'},
    @{name='extension_tests'; script='test_ext.ps1'},
    @{name='trace_disabled_compatibility'; script='verify_trace_disabled.ps1'},
    @{name='artifact_checks'; script='check_interview_artifacts.ps1'},
    @{name='summary'; script='summarize_interview_results.ps1'},
    @{name='verification'; script='verify_interview_results.ps1'}
)
$results = @()
foreach ($step in $steps) {
    $started = [DateTime]::UtcNow.ToString('o')
    try {
        $global:LASTEXITCODE = 0
        $stepArgs = @{}; if ($step.args) { $stepArgs = $step.args }
        & (Join-Path $PSScriptRoot $step.script) @stepArgs
        if ($LASTEXITCODE -ne 0) { throw "Exit code $LASTEXITCODE" }
        $results += @{step=$step.name; passed=$true; started_utc=$started}
    } catch {
        Write-Warning "$($step.name) failed: $_"
        $results += @{step=$step.name; passed=$false; started_utc=$started; error="$_"}
    }
    $results | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $Root 'results/interview/resume_status.json') -Encoding utf8
}
if (@($results | Where-Object { -not $_.passed }).Count) { throw 'Some interview checks failed. See results/interview/resume_status.json and preserved raw artifacts.' }
Write-Host 'Remaining interview verification completed.'
