<#
목적: 저장된 box RGB digest 중복과 오프라인 기대 라벨 충돌을 추적한다. 실행 판정은 변경하지 않는다.
사용법: .\scripts\diagnose_capture_duplicates.ps1
출력: results/interview/capture_duplicate_audit.json, logs/diagnose_capture_duplicates_<timestamp>.log
#>
. "$PSScriptRoot\_common.ps1"
$log = New-LogPath 'diagnose_capture_duplicates'
$ErrorActionPreference = 'Continue'
& python "$PSScriptRoot\diagnose_capture_duplicates.py" 2>&1 | ForEach-Object { $_; Add-Content $log $_ -Encoding utf8 }
if ($LASTEXITCODE -ne 0) { throw "Duplicate capture audit failed: $log" }
