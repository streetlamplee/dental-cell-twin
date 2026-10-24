<#
목적: GUI 점검. 앱을 기본 설정(크라운, 비전 꺼짐)으로 열고, 대시보드와 티칭 펜던트를 사람처럼 클릭해 본다(omni.kit.ui_test). 단계마다 앱 창 전체를 캡처하고, 단계별 PASS/FAIL 보고서를 남긴 뒤 앱을 닫는다.
  단계: 기본값 → 제품 수 입력, Build Scene → Start, View 전환 → 비전 끔 run 결과 → Vision 체크 + Reset + Start → Build Scene + Start(비전 켬) → 티칭 펜던트(생성, 조그, 저장, 재생, 내보내기, 닫기)
사용법: .\scripts\gui_check.ps1
출력: results/gui_check/<timestamp>/report.md + 단계별 PNG, logs/gui_check_<timestamp>.log
#>
. "$PSScriptRoot\_common.ps1"
Warn-IfKitRunning

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$out = Join-Path $Root "results\gui_check\$stamp"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$exec = (Join-Path $PSScriptRoot "gui_check.py") -replace '\\', '/'
$runs = (Join-Path $out "runs_root") -replace '\\', '/'
$log = New-LogPath "gui_check"
$kitArgs = "--exec `"$exec`" --/visiontwin/gui/out=`"$($out -replace '\\', '/')`" --/exts/visiontwin.factory/outputDir=`"$runs`" $KitAutomationArgs"
$ErrorActionPreference = 'Continue'
& cmd /c "`"$bat`" $kitArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match '\[gui\]|\[Error\]') { $_ }
}
Write-Host "Report: $(Join-Path $out 'report.md')  Log: $log"
