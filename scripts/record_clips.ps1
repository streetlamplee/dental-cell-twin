<#
목적: README용 부분별 클립을 녹화한다. 크라운 라인(검사 켬)에서 제품 하나(기본 #1, 미완성 가공 형상 불량)를 따라가며 라인 진입, 로봇 로딩, 5시점 검사, 언로딩, 불량 배출, 표면 티칭을 각각 실제 속도 클립으로 저장하고, ffmpeg로 클립마다 MP4와 README GIF를 만든다.
사용법: .\scripts\record_clips.ps1 [-Focus 1] [-Seed 3]
인자: -Focus  따라갈 제품 번호(seed 3: #1 미완성 가공 형상), -Seed  랜덤 시드
출력: results/demo/clips_<timestamp>/<clip>.mp4, docs/screenshots/clips/<clip>.gif (README가 참조), logs/record_clips_<timestamp>.log
필요: ffmpeg (PATH)
#>
param(
    [int]$Focus = 1,
    [int]$Seed = 3
)
. "$PSScriptRoot\_common.ps1"
Warn-IfKitRunning

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { throw "ffmpeg not found on PATH." }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outDir = Join-Path $Root "results\demo\clips_$stamp"
$frames = Join-Path $outDir "frames"
$gifDir = Join-Path $Root "docs\screenshots\clips"
New-Item -ItemType Directory -Force -Path $frames, $gifDir | Out-Null
$exec = (Join-Path $PSScriptRoot "record_clips.py") -replace '\\', '/'
$runs = (Join-Path $Root "results\smoke\demo_runs") -replace '\\', '/'
$log = New-LogPath "record_clips"
$kitArgs = "--exec `"$exec`" --/visiontwin/rec/frames=`"$($frames -replace '\\', '/')`" --/visiontwin/rec/focus=$Focus --/visiontwin/rec/seed=$Seed --/exts/visiontwin.factory/mainViewportScale=1.0 --/exts/visiontwin.factory/outputDir=`"$runs`" $KitAutomationArgs --/app/settings/persistent=0 --/app/settings/loadUserConfig=0 --/persistent/rtx/modes/rt/enabled=true --/persistent/rtx/modes/pt/enabled=false --/persistent/rtx/modes/rt2/enabled=false --/rtx/rendermode=RaytracedLighting"
$ErrorActionPreference = 'Continue'
& cmd /c "`"$bat`" $kitArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match '\[clips\]|\[Error\]') { $_ }
}
$clips = Get-ChildItem $frames -Directory | Sort-Object Name
if ($LASTEXITCODE -ne 0) { throw "Kit recording failed. Frames retained at $frames. Log: $log" }
if ($clips.Count -lt 6) { throw "Only $($clips.Count) clips recorded. Log: $log" }
foreach ($c in $clips) {
    $n = (Get-ChildItem $c.FullName -Filter *.jpg).Count
    $mp4 = Join-Path $outDir "$($c.Name).mp4"
    $gif = Join-Path $gifDir "$($c.Name).gif"
    & ffmpeg -hide_banner -loglevel error -y -framerate 30 -i (Join-Path $c.FullName "%05d.jpg") -c:v libx264 -pix_fmt yuv420p -crf 20 -preset slow -movflags +faststart $mp4
    if ($LASTEXITCODE -ne 0) { throw "MP4 encoding failed: $mp4" }
    & ffmpeg -hide_banner -loglevel error -y -i $mp4 -vf "fps=10,scale=560:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse" $gif
    if ($LASTEXITCODE -ne 0) { throw "GIF encoding failed: $gif" }
    Write-Host ("{0}: {1} frames ({2:N1} s), mp4 {3:N1} MB, gif {4:N1} MB" -f $c.Name, $n, ($n / 30), ((Get-Item $mp4).Length / 1MB), ((Get-Item $gif).Length / 1MB))
}
$concatList = Join-Path $outDir "clips.txt"
$clips | ForEach-Object { "file '$($_.Name).mp4'" } | Set-Content -LiteralPath $concatList -Encoding ascii
$combined = Join-Path $outDir "dental_cell_closeup_demo.mp4"
& ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i $concatList -c copy -movflags +faststart $combined
if ($LASTEXITCODE -ne 0) { throw "Combined video encoding failed: $combined" }
$resolvedFrames = (Resolve-Path -LiteralPath $frames).Path
$resolvedOutput = (Resolve-Path -LiteralPath $outDir).Path
if ($resolvedFrames -ne (Join-Path $resolvedOutput "frames")) { throw "Unexpected frames path: $resolvedFrames" }
Remove-Item -LiteralPath $resolvedFrames -Recurse -Force
Write-Host "Clips: $outDir  GIFs: $gifDir  Log: $log"
