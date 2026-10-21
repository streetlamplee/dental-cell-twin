<#
목적: Kit 앱과 확장을 빌드한다 (repo.bat build). 처음 빌드하면 Kit SDK와 의존 확장을 내려받는다.
사용법: .\scripts\build_app.ps1
출력: _build/windows-x86_64/release, logs/build_app_<timestamp>.log
#>
. "$PSScriptRoot\_common.ps1"

Invoke-Repo -RepoArgs @("build") -LogPath (New-LogPath "build_app")
Write-Host "Build OK"
