<#
목적: 로봇 설명(URDF + 시각용 메시 + LICENSE)을 고정 커밋에서 내려받고 SHA256을 기록/확인한다.
사용법: .\scripts\fetch_robot.ps1 [-Name rebot_b601_dm]
인자: -Name  assets/robots/sources.json의 항목 이름
출력: assets/robots/<Name>/ (저장소 상대 경로 유지), sources.json의 sha256, logs/fetch_robot_<timestamp>.log
#>
param(
    [string]$Name = "rebot_b601_dm"
)
. "$PSScriptRoot\_common.ps1"

$log = New-LogPath "fetch_robot"
$ErrorActionPreference = 'Continue'
& python (Join-Path $PSScriptRoot "fetch_robot.py") $Name 2>&1 | ForEach-Object {
    $_; Add-Content -Path $log -Value $_ -Encoding utf8
}
exit $LASTEXITCODE
