<#
목적: 이 Kit 버전의 확장 레지스트리에 원하는 확장이 있는지(있으면 최신 호환 버전) 확인한다. 아무것도 켜거나 받지 않는다.
사용법: .\scripts\probe_extensions.ps1 -Names "omni.replicator.core,omni.physx"
인자: -Names  쉼표로 구분한 확장 이름
출력: 화면(확장별 버전 또는 not found), logs/probe_extensions_<timestamp>.log
#>
param(
    [Parameter(Mandatory = $true)][string]$Names
)
. "$PSScriptRoot\_common.ps1"
Warn-IfKitRunning

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }
$exec = (Join-Path $PSScriptRoot "probe_extensions.py") -replace '\\', '/'
$log = New-LogPath "probe_extensions"
$ErrorActionPreference = 'Continue'
& cmd /c "`"$bat`" --no-window --exec `"$exec`" --/visiontwin/probe/names=`"$Names`" $KitAutomationArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match 'probe_ext\]|\[Error\]') { $_ }
}
Write-Host "Probe finished (exit $LASTEXITCODE). Log: $log"
