<#
목적: omni.replicator.core를 켜고(처음엔 레지스트리에서 받음) 이 프로젝트가 쓰는 API 시그니처를 출력한다.
사용법: .\scripts\probe_replicator.ps1
출력: 화면, logs/probe_replicator_<timestamp>.log
#>
. "$PSScriptRoot\_common.ps1"
Warn-IfKitRunning

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
$exec = (Join-Path $PSScriptRoot "probe_replicator.py") -replace '\\', '/'
$log = New-LogPath "probe_replicator"
$ErrorActionPreference = 'Continue'
& cmd /c "`"$bat`" --no-window --exec `"$exec`" $KitAutomationArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match 'probe_rep\]|\[Error\]') { $_ }
}
Write-Host "Probe finished (exit $LASTEXITCODE). Log: $log"
