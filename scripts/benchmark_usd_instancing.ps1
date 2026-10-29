<#
목적: 반복 CAD 배치의 일반 참조·인스턴스·해제 구성과 CPU 측정, 편집 제약 검증.
사용법: .\scripts\benchmark_usd_instancing.ps1
출력: results/interview/instancing/<timestamp>/manifest.json 및 USD, logs/benchmark_usd_instancing_*.log
#>
. "$PSScriptRoot\_common.ps1"
if (Get-Process kit -ErrorAction SilentlyContinue) { throw 'Run CPU benchmarks after the Kit run finishes.' }
$log = New-LogPath 'benchmark_usd_instancing'
$ErrorActionPreference = 'Continue'
& (Join-Path $Root '.venv-cad\Scripts\python.exe') "$PSScriptRoot\benchmark_usd_instancing.py" 2>&1 | ForEach-Object { $_; Add-Content $log $_ -Encoding utf8 }
if ($LASTEXITCODE -ne 0) { throw "Instancing benchmark failed: $log" }
