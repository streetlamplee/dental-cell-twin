<#
목적: USD 실험 Stage를 Kit에서 열고 반복 배치 렌더·메모리 성능을 새 프로세스로 측정.
사용법: .\scripts\benchmark_interview_render.ps1 [-Manifest <manifest.json>] [-Repeats 3]
출력: manifest 폴더/render/<구성>_<개수>_<반복>/, results/interview/composition_render/.
#>
param([string]$Manifest = '', [int]$Repeats = 3)
. "$PSScriptRoot\_interview.ps1"
if (-not $Manifest) {
    $latest = Get-ChildItem (Join-Path $Root 'results\interview\instancing') -Directory | Sort-Object Name -Descending | Select-Object -First 1
    $Manifest = Join-Path $latest.FullName 'manifest.json'
}
$manifestPath = (Resolve-Path -LiteralPath $Manifest).Path
$directory = Split-Path $manifestPath -Parent
$data = Get-Content $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
$batch = Get-Date -Format yyyyMMdd_HHmmss
foreach ($entry in $data.entries) {
    foreach ($repeat in 1..$Repeats) {
        $out = Join-Path $directory "render\$batch\$($entry.mode)_$($entry.count)_$repeat"
        Invoke-InterviewKit -Script 'render_interview_assets.py' -Out $out -TimeoutSeconds 180 -Settings @{
            '/visiontwin/interview/scene'=(Join-Path $directory $entry.scene)
            '/exts/visiontwin.factory/vision'='false'; '/app/asyncRendering'='false'
        }
        $process = Get-Content (Join-Path $out 'render.json') -Raw -Encoding utf8 | ConvertFrom-Json
        if ($null -eq $process.update_ms) { throw "Missing render measurements: $out" }
        if ($process.memory.rss_bytes -gt 8GB) { throw 'Memory guard: stop before larger configurations.' }
    }
}
Write-Host "Render measurements complete: $directory"
