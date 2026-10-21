<#
목적: 보정용 run(평가에 쓰지 않는 시드)의 정상품 프레임으로 검사기 기준 색상/채도 임계값을 정해 config/inspector.json에 저장한다.
사용법: .\scripts\calibrate_inspector.ps1 -RunDir results\runs\<보정용 run>
인자: -RunDir  보정용 run 폴더 (필수: 평가 run과 섞이지 않도록 명시)
출력: config/inspector.json, logs/calibrate_inspector_<timestamp>.log
#>
param(
    [Parameter(Mandatory = $true)][string]$RunDir
)
. "$PSScriptRoot\_common.ps1"

$log = New-LogPath "calibrate_inspector"
$ErrorActionPreference = 'Continue'
& python (Join-Path $PSScriptRoot "calibrate_inspector.py") $RunDir 2>&1 | ForEach-Object {
    $_; Add-Content -Path $log -Value $_ -Encoding utf8
}
exit $LASTEXITCODE
