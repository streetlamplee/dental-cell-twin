<#
목적: 고정 스텝/실제 시간, 뷰포트 부하와 캡처 지연·타임아웃 조건의 반복 측정.
사용법: .\scripts\run_interview_timing.ps1 [-Repeats 3] [-Products 6]
출력: results/interview/timing/<timestamp>/<조건>_<반복>/의 run과 trace.
#>
param([int]$Repeats = 3, [int]$Products = 6)
. "$PSScriptRoot\_interview.ps1"
$out = Join-Path $Root "results\interview\timing\$(Get-Date -Format yyyyMMdd_HHmmss)"
$cases = @(
    @{name='fixed_light'; dt=(1.0 / 60.0); scale=0.25; delay=0; timeout=30},
    @{name='fixed_heavy'; dt=(1.0 / 60.0); scale=1.0; delay=0; timeout=30},
    @{name='wall_light'; dt=0; scale=0.25; delay=0; timeout=30},
    @{name='wall_heavy'; dt=0; scale=1.0; delay=0; timeout=30},
    @{name='delivery_delay'; dt=(1.0 / 60.0); scale=0.25; delay=0.5; timeout=30},
    @{name='wall_timeout'; dt=(1.0 / 60.0); scale=0.25; delay=1.0; timeout=0.3},
    @{name='update_budget'; dt=(1.0 / 60.0); scale=0.25; delay=1.0; timeout=30; updates=2}
)
foreach ($case in $cases) {
    foreach ($repeat in 1..$Repeats) {
        $updates = if ($case.ContainsKey('updates')) { $case.updates } else { 180 }
        Invoke-InterviewKit -Script 'collect_frames.py' -Out (Join-Path $out "$($case.name)_$repeat") -Settings @{
            '/exts/visiontwin.factory/part'='box'; '/exts/visiontwin.factory/vision'='true'
            '/exts/visiontwin.factory/trace'='true'; '/exts/visiontwin.factory/seed'=42
            '/exts/visiontwin.factory/maxProducts'=$Products; '/exts/visiontwin.factory/speed'=1.5
            '/exts/visiontwin.factory/fixedDt'=$case.dt; '/exts/visiontwin.factory/mainViewportScale'=$case.scale
            '/exts/visiontwin.factory/captureDeliveryDelayS'=$case.delay
            '/exts/visiontwin.factory/captureWallTimeoutS'=$case.timeout
            '/exts/visiontwin.factory/captureUpdateBudget'=$updates
        }
    }
}
Write-Host "Timing measurements complete: $out"
