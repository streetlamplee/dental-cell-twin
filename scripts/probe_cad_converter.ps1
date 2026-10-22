<#
목적: Gate C 진단. 이 프로젝트의 Kit에서 USD converter(omni.kit.converter.hoops_core)로 STP 1개를 USD로 바꿔 본다.
사용법: .\scripts\probe_cad_converter.ps1 -Stp <file.stp>
인자: -Stp  변환할 STP 파일
출력: results/smoke/cad_probe/<이름>.usd, logs/probe_cad_converter_<timestamp>.log
#>
param(
    [Parameter(Mandatory = $true)][string]$Stp
)
. "$PSScriptRoot\_common.ps1"
Warn-IfKitRunning

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }
$src = (Resolve-Path $Stp).Path -replace '\\', '/'
$out = (Join-Path $Root ("results\smoke\cad_probe\" + [IO.Path]::GetFileNameWithoutExtension($Stp) + ".usd")) -replace '\\', '/'
$exec = (Join-Path $PSScriptRoot "probe_cad_converter.py") -replace '\\', '/'
$log = New-LogPath "probe_cad_converter"

$ErrorActionPreference = 'Continue'
& cmd /c "`"$bat`" --no-window --exec `"$exec`" --/visiontwin/cad/in=`"$src`" --/visiontwin/cad/out=`"$out`" $KitAutomationArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match 'probe_cad|\[Error\]|hoops') { $_ }
}
Write-Host "Probe finished (exit $LASTEXITCODE). Log: $log"
