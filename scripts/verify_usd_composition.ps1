<#
목적: USD 변환 충돌·레이어 복원·VariantSet·단위 변환 최소 예제 생성 및 검증.
사용법: .\scripts\verify_usd_composition.ps1
출력: results/interview/composition/<timestamp>/, logs/verify_usd_composition_<timestamp>.log
#>
. "$PSScriptRoot\_common.ps1"
$log = New-LogPath 'verify_usd_composition'
& (Join-Path $Root '.venv-cad\Scripts\python.exe') "$PSScriptRoot\verify_usd_composition.py" 2>&1 | ForEach-Object { $_; Add-Content $log $_ -Encoding utf8 }
if ($LASTEXITCODE -ne 0) { throw "USD composition verification failed: $log" }
