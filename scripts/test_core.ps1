<#
목적: Kit 없이 실행되는 순수 Python 단위 테스트(tests/)를 시스템 Python + pytest로 실행한다.
사용법: .\scripts\test_core.ps1 [-Filter conveyor]
인자: -Filter  pytest -k 표현식 (기본: 전체)
출력: 화면 + logs/test_core_<timestamp>.log
#>
param(
    [string]$Filter = ""
)
. "$PSScriptRoot\_common.ps1"

$log = New-LogPath "test_core"
$pytestArgs = @("-m", "pytest", (Join-Path $Root "tests"), "-q")
if ($Filter) { $pytestArgs += @("-k", $Filter) }

$ErrorActionPreference = 'Continue'
& python @pytestArgs 2>&1 | ForEach-Object {
    $_
    Add-Content -Path $log -Value $_ -Encoding utf8
}
$code = $LASTEXITCODE
if ($code -ne 0) { Write-Host "Tests FAILED (exit $code). Log: $log"; exit $code }
Write-Host "Tests passed. Log: $log"
