<#
목적: assets/parts/sources.json에 적힌 실제 CAD 부품 STEP을 내려받고 SHA256을 확인/기록한다.
사용법: .\scripts\fetch_parts.ps1 [-Name kicad_dip8]
인자: -Name  특정 부품(상태 무관, 후보 평가용). 기본: status가 selected인 부품
출력: assets/parts/raw/<name>.step, logs/fetch_parts_<timestamp>.log
#>
param(
    [string]$Name = ""
)
. "$PSScriptRoot\_common.ps1"

$log = New-LogPath "fetch_parts"
$pyArgs = @((Join-Path $PSScriptRoot "fetch_parts.py"))
if ($Name) { $pyArgs += $Name }
$ErrorActionPreference = 'Continue'
& python @pyArgs 2>&1 | ForEach-Object { $_; Add-Content -Path $log -Value $_ -Encoding utf8 }
exit $LASTEXITCODE
