<#
목적: Gate B 진단. 검사 카메라 프레임을 버퍼로 받는 방법(A: ViewportWidget, B: ViewportWindow)을 비교한다.
사용법: .\scripts\probe_capture.ps1
출력: results/smoke/probe_<timestamp>_A.png / _B.png (성공한 방법만), logs/probe_capture_<timestamp>.log
#>
. "$PSScriptRoot\_common.ps1"

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }

$outDir = Join-Path $Root "results\smoke"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }
$png = (Join-Path $outDir ("probe_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".png")) -replace '\\', '/'
$exec = (Join-Path $PSScriptRoot "probe_capture.py") -replace '\\', '/'
$log = New-LogPath "probe_capture"

$ErrorActionPreference = 'Continue'
& cmd /c "`"$bat`" --exec `"$exec`" --/visiontwin/probe/out=`"$png`" --/exts/visiontwin.factory/outputDir=`"$($outDir -replace '\\', '/')/probe_runs`" $KitAutomationArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match 'probe_capture|\[Error\]') { $_ }
}
Write-Host "Probe finished (exit $LASTEXITCODE). Log: $log"
