<#
목적: 검사 셀(스핀들 카메라, 시점 5개)의 합성 학습 데이터를 Omniverse Replicator로 만든다(도메인 랜덤화: 조명, 셰이드, 제품 방향/위치, 카메라 흔들림).
사용법: .\scripts\generate_dataset.ps1 -Out datasets\crown_sdg -Samples 1600 [-Seed 0]
인자: -Out  출력 폴더, -Samples  제품 샘플 수(이미지 = 샘플 x 시점 5), -Seed  랜덤 시드
출력: <Out>/replicator/rgb_*.png, <Out>/labels.csv, <Out>/dataset.json, logs/generate_dataset_<timestamp>.log
#>
param(
    [Parameter(Mandatory = $true)][string]$Out,
    [int]$Samples = 1600,
    [int]$Seed = 0
)
. "$PSScriptRoot\_common.ps1"
Warn-IfKitRunning

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }
$outFull = [IO.Path]::GetFullPath((Join-Path (Get-Location) $Out))
if (Test-Path $outFull) { throw "Output exists: $outFull (choose a new folder)" }
New-Item -ItemType Directory -Force -Path $outFull | Out-Null
$exec = (Join-Path $PSScriptRoot "generate_dataset.py") -replace '\\', '/'
$log = New-LogPath "generate_dataset"
$o = $outFull -replace '\\', '/'
# SyntheticData (Replicator annotators) needs a Fabric frame history of at least 3.
$kitArgs = "--exec `"$exec`" --/visiontwin/sdg/out=`"$o`" --/visiontwin/sdg/samples=$Samples --/visiontwin/sdg/seed=$Seed --/app/settings/fabricDefaultStageFrameHistoryCount=3 --/exts/visiontwin.factory/part=crown $KitAutomationArgs"
$ErrorActionPreference = 'Continue'
& cmd /c "`"$bat`" $kitArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match '\[sdg\]|\[Error\]') { $_ }
}
Write-Host "Dataset generation finished (exit $LASTEXITCODE). Log: $log"
