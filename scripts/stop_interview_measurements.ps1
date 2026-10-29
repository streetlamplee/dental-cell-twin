<#
목적: 현재 작업이 시작한 측정 실행기와 Kit만 종료하고 중단 위치를 기록.
사용법: .\scripts\stop_interview_measurements.ps1 -RunnerId <PID> -KitId <PID>
출력: results/interview/interrupted.json. 다른 Kit/PowerShell 프로세스는 종료하지 않음.
#>
param([Parameter(Mandatory=$true)][int]$RunnerId, [Parameter(Mandatory=$true)][int]$KitId)
. "$PSScriptRoot\_common.ps1"
$runner = Get-CimInstance Win32_Process -Filter "ProcessId=$RunnerId"
$kitInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$KitId"
if (-not $runner -or $runner.CommandLine -notlike '*run_interview_measurements.ps1*') { throw 'Runner identity does not match.' }
if (-not $kitInfo -or $kitInfo.Name -ne 'kit.exe' -or $kitInfo.CommandLine -notlike "*$Root*results\interview\baseline\after_*" ) { throw 'Kit identity does not match this experiment.' }
$kitProcess = Get-Process -Id $KitId
$kitHandle = $kitProcess.Handle
$commandParent = $kitInfo.ParentProcessId
# Stop the orchestrator first so it cannot launch the next GPU process.
Stop-Process -Id $RunnerId -Force
$requestedClose = $kitProcess.CloseMainWindow()
if (-not $kitProcess.WaitForExit(8000)) {
    & taskkill /PID $KitId /T /F | Out-Null
    $kitProcess.WaitForExit()
}
$parent = Get-CimInstance Win32_Process -Filter "ProcessId=$commandParent"
if ($parent -and $parent.Name -eq 'cmd.exe' -and $parent.CommandLine -like "*$Root*collect_frames.py*") {
    Stop-Process -Id $commandParent -Force -ErrorAction SilentlyContinue
}
@{status='interrupted_by_user'; stopped_utc=[DateTime]::UtcNow.ToString('o'); runner_id=$RunnerId; kit_id=$KitId;
    graceful_close_requested=$requestedClose; command=$kitInfo.CommandLine;
    resume='See docs/2026-10-26 면접 준비용 Omniverse 고도화 구현.md'} |
    ConvertTo-Json -Depth 4 | Set-Content (Join-Path $Root 'results\interview\interrupted.json') -Encoding utf8
Write-Host 'Stopped the measurement runner and its Kit process. Results preserved.'
