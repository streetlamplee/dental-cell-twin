<#
목적: visiontwin.factory 확장의 Kit 내부 테스트(omni.kit.test)를 실행한다. 빌드가 먼저 되어 있어야 한다.
사용법: .\scripts\test_ext.ps1
출력: 화면 + logs/test_ext_<timestamp>.log, 상세 결과는 _testoutput/
#>
. "$PSScriptRoot\_common.ps1"

$bat = Join-Path $Root "_build\windows-x86_64\release\tests-visiontwin.factory.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }

$log = New-LogPath "test_ext"
$ErrorActionPreference = 'Continue'
& cmd /c "`"$bat`" 2>&1" | ForEach-Object {
    $_
    Add-Content -Path $log -Value $_ -Encoding utf8
}
$code = $LASTEXITCODE
if ($code -ne 0) { Write-Host "Extension tests FAILED (exit $code). Log: $log"; exit $code }
Write-Host "Extension tests passed. Log: $log"
