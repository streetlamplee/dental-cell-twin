<#
목적: 50개 인스턴스·같은 해상도에서 CAD LOD 0/3/4의 렌더 비용을 각각 3회 측정.
사용법: .\scripts\benchmark_interview_lod.ps1
출력: results/interview/lod/<timestamp>/의 fixture, 품질 참조표, render 결과.
#>
. "$PSScriptRoot\_common.ps1"
if (Get-Process kit -ErrorAction SilentlyContinue) { throw 'Close existing Kit before the LOD benchmark.' }
$log = New-LogPath 'benchmark_interview_lod'
& (Join-Path $Root '.venv-cad\Scripts\python.exe') "$PSScriptRoot\prepare_interview_lod.py" 2>&1 | ForEach-Object { $_; Add-Content $log $_ -Encoding utf8 }
if ($LASTEXITCODE -ne 0) { throw "LOD fixture preparation failed: $log" }
$latest = Get-ChildItem (Join-Path $Root 'results\interview\lod') -Directory | Sort-Object Name -Descending | Select-Object -First 1
& "$PSScriptRoot\benchmark_interview_render.ps1" -Manifest (Join-Path $latest.FullName 'manifest.json') -Repeats 3
