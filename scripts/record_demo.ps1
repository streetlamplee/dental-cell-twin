<#
목적: 데모 영상을 자동으로 녹화한다. 데모 흐름(크라운 라인, 화면 자동 전환, 티칭 재생)의 메인 뷰포트를 1280x720 프레임으로 저장하고(자막·카운터 포함), 결과 이미지를 붙인 뒤 ffmpeg로 MP4(H.264, 30 fps, 실제 속도)와 README용 GIF를 만든다.
사용법: .\scripts\record_demo.ps1 [-Products 4] [-Seed 42]
인자: -Products  투입 제품 수, -Seed  랜덤 시드
출력: results/demo/dental_cell_twin_demo_<timestamp>.mp4, ..._preview.gif, logs/record_demo_<timestamp>.log (프레임 폴더는 끝나면 지움)
필요: ffmpeg (PATH)
#>
param(
    [int]$Products = 4,
    [int]$Seed = 42
)
. "$PSScriptRoot\_common.ps1"
Warn-IfKitRunning

$bat = Join-Path $Root "_build\windows-x86_64\release\visiontwin.app.kit.bat"
if (-not (Test-Path $bat)) { throw "Not built yet. Run .\scripts\build_app.ps1 first." }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { throw "ffmpeg not found on PATH." }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outDir = Join-Path $Root "results\demo"
$frames = Join-Path $outDir "frames_$stamp"
New-Item -ItemType Directory -Force -Path $frames | Out-Null
$mp4 = Join-Path $outDir "dental_cell_twin_demo_$stamp.mp4"
$gif = Join-Path $outDir "dental_cell_twin_demo_${stamp}_preview.gif"
$stills = @("docs\screenshots\readme_views.png", "docs\screenshots\readme_fig_model.png") |
    ForEach-Object { (Join-Path $Root $_) -replace '\\', '/' }
$exec = (Join-Path $PSScriptRoot "record_demo.py") -replace '\\', '/'
$runs = (Join-Path $Root "results\smoke\demo_runs") -replace '\\', '/'
$log = New-LogPath "record_demo"
$kitArgs = "--exec `"$exec`" --/visiontwin/rec/frames=`"$($frames -replace '\\', '/')`" --/visiontwin/rec/products=$Products --/visiontwin/rec/seed=$Seed --/visiontwin/rec/stills=`"$($stills -join ';')`" --/exts/visiontwin.factory/mainViewportScale=1.0 --/exts/visiontwin.factory/outputDir=`"$runs`" $KitAutomationArgs"
$ErrorActionPreference = 'Continue'
& cmd /c "`"$bat`" $kitArgs 2>&1" | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match '\[record\]|\[Error\]') { $_ }
}
$n = (Get-ChildItem $frames -Filter *.jpg).Count
if ($n -lt 30) { throw "Only $n frames recorded. Log: $log" }
& ffmpeg -hide_banner -loglevel error -y -framerate 30 -i (Join-Path $frames "%05d.jpg") -c:v libx264 -pix_fmt yuv420p -crf 20 -preset slow -movflags +faststart $mp4
& ffmpeg -hide_banner -loglevel error -y -ss 4 -t 12 -i $mp4 -vf "fps=10,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse" $gif
Remove-Item -Recurse -Force $frames
Write-Host ("Recorded {0} frames ({1:N0} s): {2} ({3:N1} MB), preview {4} ({5:N1} MB). Log: {6}" -f $n, ($n / 30), $mp4, ((Get-Item $mp4).Length / 1MB), $gif, ((Get-Item $gif).Length / 1MB), $log)
