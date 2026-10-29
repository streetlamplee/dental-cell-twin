<#
목적: 면접 검증 스크립트의 Kit 실행, 외부 watchdog, 환경 기록 공통 처리.
사용법: dot-source 후 Invoke-InterviewKit -Script ... -Out ... -Settings ...
출력: 지정 폴더의 stdout.log, stderr.log, process.json. 제한시간 초과는 실패.
#>
. "$PSScriptRoot\_common.ps1"

function Invoke-InterviewKit {
    param([string]$Script, [string]$Out, [hashtable]$Settings = @{}, [int]$TimeoutSeconds = 900)
    if (Get-Process kit -ErrorAction SilentlyContinue) { throw "Close the existing Kit before running GPU experiments." }
    $resolvedOut = [IO.Path]::GetFullPath($Out)
    if (Test-Path -LiteralPath (Join-Path $resolvedOut 'stdout.log')) { throw "Experiment output already exists: $resolvedOut" }
    New-Item -ItemType Directory -Path $resolvedOut -Force | Out-Null
    $launcher = Join-Path $Root '_build\windows-x86_64\release\visiontwin.app.kit.bat'
    $scriptPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $Script))
    $argsText = "--exec `"$scriptPath`" $KitAutomationArgs"
    $allSettings = @{'/visiontwin/interview/out' = $resolvedOut; '/exts/visiontwin.factory/outputDir' = $resolvedOut}
    foreach ($key in $Settings.Keys) { $allSettings[$key] = $Settings[$key] }
    foreach ($key in ($allSettings.Keys | Sort-Object)) {
        $value = [Convert]::ToString($allSettings[$key], [Globalization.CultureInfo]::InvariantCulture)
        $argsText += " --$key=`"$value`""
    }
    $start = [DateTime]::UtcNow
    $sourceHashes = @{}
    foreach ($name in @('extension.py','frame_provider.py','capture_runtime.py','runtime_session.py')) {
        $file = Join-Path $Root "source\extensions\visiontwin.factory\visiontwin\factory\$name"
        if (Test-Path -LiteralPath $file) { $sourceHashes[$name] = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash }
    }
    $proc = Start-Process -FilePath $env:ComSpec -ArgumentList "/d /c `"`"$launcher`" $argsText`"" -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $resolvedOut 'stdout.log') -RedirectStandardError (Join-Path $resolvedOut 'stderr.log')
    $processHandle = $proc.Handle  # retain the handle so PS 5.1 can read ExitCode after exit
    $timedOut = $false
    while (-not $proc.WaitForExit(1000)) {
        if (([DateTime]::UtcNow - $start).TotalSeconds -gt $TimeoutSeconds) {
            $timedOut = $true
            # Only the process tree created above belongs to this experiment.
            & taskkill /PID $proc.Id /T /F | Out-Null
            $proc.WaitForExit()
            break
        }
    }
    $meta = @{
        started_utc = $start.ToString('o'); wall_s = ([DateTime]::UtcNow - $start).TotalSeconds
        exit_code = $proc.ExitCode; watchdog_timeout = $timedOut; settings = $allSettings
        source_commit = (& git -C $Root rev-parse HEAD); working_tree = @(& git -C $Root status --short)
        gpu = @(& nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader)
        os = [Environment]::OSVersion.ToString(); script = $Script
        source_sha256_at_launch = $sourceHashes
        automation_args = $KitAutomationArgs
    }
    $meta | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $resolvedOut 'process.json') -Encoding utf8
    $archiveName = 'interview_' + [IO.Path]::GetFileNameWithoutExtension($Script)
    Copy-Item -LiteralPath (Join-Path $resolvedOut 'stdout.log') -Destination (New-LogPath $archiveName)
    Copy-Item -LiteralPath (Join-Path $resolvedOut 'stderr.log') -Destination (New-LogPath ($archiveName + '_stderr'))
    Write-Host "Kit exit=$($proc.ExitCode) watchdog=$timedOut out=$resolvedOut"
    if ($timedOut -or $proc.ExitCode -ne 0) { throw "Kit experiment failed: $resolvedOut" }
}
