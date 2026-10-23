<#
목적: 로봇 USD(urdf_mesh_to_usd 결과)를 관절 자세 하나로 놓고 Kit에서 렌더해 PNG로 저장한다(FK, kinematics.json 사용).
사용법: .\scripts\render_robot_pose.ps1 -Usd assets\robots\usd\rebot_b601_dm.usd [-Pose "joint2=-1.0,joint3=-1.2"]
인자: -Usd  로봇 USD(옆에 .kinematics.json 필요), -Pose  "관절=라디안(또는 m)" 목록(기본: 홈 자세)
출력: results/smoke/robot_<이름>_<timestamp>.png, logs/render_robot_pose_<timestamp>.log
#>
param(
    [Parameter(Mandatory = $true)][string]$Usd,
    [string]$Pose = ""
)
. "$PSScriptRoot\_common.ps1"
Warn-IfKitRunning

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }
$usdFull = (Resolve-Path $Usd).Path -replace '\\', '/'
$outDir = Join-Path $Root "results\smoke"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$png = (Join-Path $outDir ("robot_" + [IO.Path]::GetFileNameWithoutExtension($Usd) + "_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".png")) -replace '\\', '/'
$exec = (Join-Path $PSScriptRoot "render_robot_pose.py") -replace '\\', '/'
$log = New-LogPath "render_robot_pose"
$ErrorActionPreference = 'Continue'
& cmd /c "`"$bat`" --exec `"$exec`" --/visiontwin/robot/usd=`"$usdFull`" --/visiontwin/robot/pose=`"$Pose`" --/visiontwin/robot/out=`"$png`" --/exts/visiontwin.factory/part=box $KitAutomationArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match 'render_robot\]|\[Error\]') { $_ }
}
if (-not (Test-Path $png)) { Write-Host "Render FAILED. Log: $log"; exit 1 }
Write-Host "Robot render OK: $png"
