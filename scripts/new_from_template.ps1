<#
목적: 저장된 playback 파일로 앱/확장을 템플릿에서 생성한다 (대화형 프롬프트 없음).
사용법: .\scripts\new_from_template.ps1 -PlaybackFile scripts\replay\visiontwin_app.toml
인자: -PlaybackFile  scripts/replay/ 아래의 toml 파일
출력: source/apps 또는 source/extensions 아래 생성물, logs/new_from_template_<timestamp>.log
#>
param(
    [Parameter(Mandatory = $true)][string]$PlaybackFile
)
. "$PSScriptRoot\_common.ps1"

$full = Resolve-Path $PlaybackFile
Invoke-Repo -RepoArgs @("template", "replay", "`"$full`"") -LogPath (New-LogPath "new_from_template")
