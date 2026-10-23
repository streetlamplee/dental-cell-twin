<#
목적: Kit 프로세스 안에서 신경망 추론이 되는지 확인한다(ONNX Runtime DirectML/CPU, 무작위 소형 CNN, 640x480 입력).
사용법: .\scripts\probe_onnx_in_kit.ps1
출력: 화면(설치 결과, 사용 가능한 provider, provider별 추론 시간), logs/probe_onnx_in_kit_<timestamp>.log
주의: 처음 실행하면 Kit의 Python에 onnx, onnxruntime-directml을 pip로 설치한다(omni.kit.pipapi).
#>
. "$PSScriptRoot\_common.ps1"
Warn-IfKitRunning

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }
$exec = (Join-Path $PSScriptRoot "probe_onnx_in_kit.py") -replace '\\', '/'
$log = New-LogPath "probe_onnx_in_kit"
$ErrorActionPreference = 'Continue'
& cmd /c "`"$bat`" --no-window --exec `"$exec`" $KitAutomationArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match 'probe_onnx\]|\[Error\]') { $_ }
}
Write-Host "Probe finished (exit $LASTEXITCODE). Log: $log"
