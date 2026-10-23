<#
목적: 표면별 티칭 증빙. 원점 + C축 블록 5면 티칭점을 만들어 점마다 기계 근접 화면을 저장하고, 검증표(각도 오차, 중심 어긋남, 거리, 축 한계)를 쓴다.
사용법: .\scripts\render_teach_program.ps1 [-StandoffMm 20] [-CloseMm 10]
인자: -StandoffMm  공구 끝과 면 사이 거리, -CloseMm  도달 가능 여부만 확인할 더 가까운 거리
출력: results/teach/<timestamp>/ (점별 PNG, contact_sheet.png, report.md/json, teach_program_*.json), logs/render_teach_program_<timestamp>.log
#>
param(
    [double]$StandoffMm = 20,
    [double]$CloseMm = 10
)
. "$PSScriptRoot\_common.ps1"
Warn-IfKitRunning

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }
$out = (Join-Path $Root ("results\teach\" + (Get-Date -Format "yyyyMMdd_HHmmss"))) -replace '\\', '/'
$exec = (Join-Path $PSScriptRoot "render_teach_program.py") -replace '\\', '/'
$inv = [Globalization.CultureInfo]::InvariantCulture
$log = New-LogPath "render_teach_program"
$ErrorActionPreference = 'Continue'
& cmd /c "`"$bat`" --exec `"$exec`" --/visiontwin/teach/out=`"$out`" --/visiontwin/teach/standoffMm=$($StandoffMm.ToString($inv)) --/visiontwin/teach/closeMm=$($CloseMm.ToString($inv)) --/exts/visiontwin.factory/part=crown --/exts/visiontwin.factory/mainViewportScale=1.0 $KitAutomationArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match '\[teach\]|\[Error\]') { $_ }
}
Write-Host "Teach render finished (exit $LASTEXITCODE). Output: $out  Log: $log"
