<#
목적: 구현 후 면접 검증 측정을 GPU 동시 실행 없이 순서대로 완료.
사용법: .\scripts\run_interview_measurements.ps1
출력: timing, instancing render, composition Kit, after baseline, 비교표와 테스트 로그.
#>
. "$PSScriptRoot\_common.ps1"
& "$PSScriptRoot\run_interview_timing.ps1"
& "$PSScriptRoot\benchmark_interview_render.ps1"
& "$PSScriptRoot\render_usd_composition.ps1"
& "$PSScriptRoot\run_interview_baseline.ps1" -Label after -Products 30
& "$PSScriptRoot\compare_interview_baselines.ps1"
& "$PSScriptRoot\test_core.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Final core checks failed.' }
& "$PSScriptRoot\check_interview_artifacts.ps1"
& "$PSScriptRoot\summarize_interview_results.ps1"
Write-Host 'Interview measurements completed.'
