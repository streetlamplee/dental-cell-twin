<#
목적: 빌드된 VisionTwin GUI 앱을 실행한다. 첫 실행은 셰이더 컴파일로 수 분 걸릴 수 있다.
사용법: .\scripts\launch_app.ps1
출력: Kit 창. Kit 로그는 _build/windows-x86_64/release/logs/ 아래에 남는다.
#>
. "$PSScriptRoot\_common.ps1"

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }

& cmd /c "`"$bat`""
exit $LASTEXITCODE
