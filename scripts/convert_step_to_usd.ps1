<#
목적: STEP 파일을 USD converter(omni.kit.converter.hoops_core)로 USD로 변환한다. 옵션은 config/cad_converter_options.json의 프로파일(machine/product/legacy).
사용법: .\scripts\convert_step_to_usd.ps1 -Stp assets\cad\teeth_mill.stp [-Out assets\cad\teeth_mill.usd] [-Profile product] [-TessLOD n]
인자: -Stp 입력 STEP, -Out 출력 USD (기본: 입력과 같은 폴더, 같은 이름 .usd),
      -Profile 변환 프로파일, -TessLOD 프로파일의 테셀레이션 LOD(0~4) 대신 쓸 값(LOD 비교용)
출력: USD 파일, <USD>.convert.json(변환기 버전, 옵션, 원본 SHA256, 시간), logs/convert_step_to_usd_<timestamp>.log
#>
param(
    [Parameter(Mandatory = $true)][string]$Stp,
    [string]$Out = "",
    [string]$Profile = "product",
    [string]$TessLOD = ""
)
. "$PSScriptRoot\_common.ps1"
Warn-IfKitRunning

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }
$src = (Resolve-Path $Stp).Path
if (-not $Out) { $Out = [IO.Path]::ChangeExtension($src, ".usd") }
$dst = [IO.Path]::GetFullPath($Out) -replace '\\', '/'
$opts = (Join-Path $Root "config\cad_converter_options.json") -replace '\\', '/'
$exec = (Join-Path $PSScriptRoot "convert_step_to_usd.py") -replace '\\', '/'
$log = New-LogPath "convert_step_to_usd"

$ErrorActionPreference = 'Continue'
& cmd /c "`"$bat`" --no-window --exec `"$exec`" --/visiontwin/cad/in=`"$($src -replace '\\', '/')`" --/visiontwin/cad/out=`"$dst`" --/visiontwin/cad/options=`"$opts`" --/visiontwin/cad/profile=$Profile --/visiontwin/cad/tessLOD=`"$TessLOD`" $KitAutomationArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match 'convert_step\]|\[Error\]') { $_ }
}
$code = $LASTEXITCODE
if ($code -ne 0 -or -not (Test-Path $dst)) { Write-Host "Conversion FAILED (exit $code). Log: $log"; exit 1 }
Write-Host "Conversion OK: $dst"
