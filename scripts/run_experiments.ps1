<#
목적: 실험 설정 파일(experiments/*.json)의 조건을 차례로 실행한다. 이미 끝난 조건(summary.json 있음)은 건너뛰므로 중단 후 다시 실행해도 된다.
사용법: .\scripts\run_experiments.ps1 -Config experiments\day9.json
인자: -Config  실험 설정 JSON
출력: results/experiments/<name>/runs/<run>/ (조건마다 1개), logs/run_experiments_<timestamp>.log
#>
param(
    [Parameter(Mandatory = $true)][string]$Config
)
. "$PSScriptRoot\_common.ps1"
Warn-IfKitRunning

$cfg = Get-Content (Resolve-Path $Config) -Raw -Encoding utf8 | ConvertFrom-Json
$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
$exec = (Join-Path $PSScriptRoot "collect_frames.py") -replace '\\', '/'
$outDir = Join-Path $Root "results\experiments\$($cfg.name)"
$log = New-LogPath "run_experiments"
$inv = [Globalization.CultureInfo]::InvariantCulture
$ErrorActionPreference = 'Continue'

function Find-DoneRun([string]$condition) {
    $runs = Join-Path $outDir "runs"
    if (-not (Test-Path $runs)) { return $null }
    foreach ($d in Get-ChildItem $runs -Directory) {
        $rj = Join-Path $d.FullName "run.json"
        if ((Test-Path (Join-Path $d.FullName "summary.json")) -and (Test-Path $rj)) {
            if ((Get-Content $rj -Raw | ConvertFrom-Json).condition -eq $condition) { return $d.FullName }
        }
    }
    return $null
}

$i = 0
foreach ($r in $cfg.runs) {
    $i++
    $done = Find-DoneRun $r.condition
    if ($done) { Write-Host "[$i/$($cfg.runs.Count)] $($r.condition): done already ($done)"; continue }
    $set = @{ part = $r.part; lighting = $r.lighting; seed = $r.seed; maxProducts = $r.products;
              speed = ([double]$r.speed).ToString($inv); experiment = $cfg.name; condition = $r.condition }
    if ($r.spawn_interval) { $set.spawnInterval = ([double]$r.spawn_interval).ToString($inv) }
    if ($r.decision) { $set.decision = $r.decision }
    $setArgs = ($set.GetEnumerator() | ForEach-Object { "--/exts/visiontwin.factory/$($_.Key)=$($_.Value)" }) -join " "
    $kitArgs = "--exec `"$exec`" $setArgs --/exts/visiontwin.factory/outputDir=`"$($outDir -replace '\\', '/')`" $KitAutomationArgs"
    $t0 = Get-Date
    Write-Host "[$i/$($cfg.runs.Count)] $($r.condition): running ..."
    & cmd /c "`"$bat`" $kitArgs 2>&1" | ForEach-Object {
        Add-Content -Path $log -Value $_ -Encoding utf8
        if ($_ -match 'collect_frames\] summary') { $_ }
    }
    $wall = ((Get-Date) - $t0).TotalSeconds
    $ok = Find-DoneRun $r.condition
    Write-Host ("[{0}/{1}] {2}: {3} ({4:N0} s wall)" -f $i, $cfg.runs.Count, $r.condition, $(if ($ok) { "OK $ok" } else { "FAILED (exit $LASTEXITCODE)" }), $wall)
}
Write-Host "Experiment $($cfg.name) finished. Log: $log"
