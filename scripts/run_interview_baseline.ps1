<#
목적: 변경 전후 box/crown 기준 실행을 각각 두 번 수집하고 감사·재현 비교.
사용법: .\scripts\run_interview_baseline.ps1 [-Label before] [-Products 30] [-BatchDirectory <중단 배치>]
출력: results/interview/baseline/<label>_<timestamp>/. 기존 결과를 덮어쓰지 않음.
#>
param([string]$Label = 'before', [int]$Products = 30, [string]$BatchDirectory = '')
. "$PSScriptRoot\_interview.ps1"
$out = Join-Path $Root "results\interview\baseline\${Label}_$(Get-Date -Format yyyyMMdd_HHmmss)"
if ($BatchDirectory) { $out = (Resolve-Path -LiteralPath $BatchDirectory).Path }
$repeatFailures = @()
$auditFailures = @()
foreach ($part in @('box', 'crown')) {
    $runs = @()
    foreach ($repeat in 1..2) {
        $dir = Join-Path $out "${part}_$repeat"
        $metaPath = Join-Path $dir 'process.json'
        if (Test-Path -LiteralPath $metaPath) {
            $meta = Get-Content -LiteralPath $metaPath -Raw -Encoding utf8 | ConvertFrom-Json
            if ($meta.exit_code -ne 0 -or $meta.watchdog_timeout -or
                $meta.settings.'/exts/visiontwin.factory/part' -ne $part -or
                $meta.settings.'/exts/visiontwin.factory/maxProducts' -ne $Products) {
                throw "Cannot reuse failed or mismatched baseline: $dir"
            }
            $expectedSettings = @{
                '/exts/visiontwin.factory/seed'=42; '/exts/visiontwin.factory/speed'=0.5
                '/exts/visiontwin.factory/vision'='true'; '/exts/visiontwin.factory/trace'='true'
            }
            foreach ($key in $expectedSettings.Keys) {
                if ([string]$meta.settings.$key -ne [string]$expectedSettings[$key]) {
                    throw "Cannot reuse different baseline setting: $key ($dir)"
                }
            }
            if ($meta.automation_args -ne $KitAutomationArgs) { throw "Automation policy differs: start a new baseline batch ($dir)" }
            foreach ($name in @('extension.py','frame_provider.py','capture_runtime.py','runtime_session.py')) {
                $file = Join-Path $Root "source\extensions\visiontwin.factory\visiontwin\factory\$name"
                if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $meta.source_sha256_at_launch.$name) {
                    throw "Source changed since baseline: $name ($dir)"
                }
            }
            Write-Host "Reusing completed baseline: $dir"
        } else {
            Invoke-InterviewKit -Script 'collect_frames.py' -Out $dir -Settings @{
            '/exts/visiontwin.factory/part'=$part; '/exts/visiontwin.factory/vision'='true'
            '/exts/visiontwin.factory/seed'=42; '/exts/visiontwin.factory/maxProducts'=$Products
            '/exts/visiontwin.factory/speed'=0.5; '/exts/visiontwin.factory/trace'='true'
            }
        }
        $run = Get-ChildItem (Join-Path $dir 'runs') -Directory | Select-Object -First 1
        & "$PSScriptRoot\check_run.ps1" -RunDir $run.FullName
        if ($LASTEXITCODE -ne 0) { $auditFailures += $run.FullName }
        $runs += $run.FullName
    }
    & "$PSScriptRoot\compare_runs.ps1" -RunA $runs[0] -RunB $runs[1]
    if ($LASTEXITCODE -ne 0) { $repeatFailures += $part }
}
if ($repeatFailures.Count -or $auditFailures.Count) { throw "Baseline failed: repeat differences=$($repeatFailures -join ', '); audit failures=$($auditFailures.Count). All four runs preserved: $out" }
Write-Host "Baseline complete: $out"
