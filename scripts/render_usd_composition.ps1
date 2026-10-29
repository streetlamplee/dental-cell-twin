<#
목적: 최근 USD 합성 검증 예제를 Kit에서 열고 렌더·재열기 호환성을 확인.
사용법: .\scripts\render_usd_composition.ps1
출력: results/interview/composition/<최근실험>/kit/<timestamp>/render.json, frame.png.
#>
. "$PSScriptRoot\_interview.ps1"
$latest = Get-ChildItem (Join-Path $Root 'results\interview\composition') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$out = Join-Path $latest.FullName "kit\$(Get-Date -Format yyyyMMdd_HHmmss)"
Invoke-InterviewKit -Script 'render_interview_assets.py' -Out $out -TimeoutSeconds 240 -Settings @{
    '/visiontwin/interview/scene'=(Join-Path $latest.FullName 'composed.usda')
    '/exts/visiontwin.factory/vision'='false'; '/app/asyncRendering'='false'
}
