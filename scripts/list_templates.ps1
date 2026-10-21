<#
목적: kit-app-template에서 사용할 수 있는 앱/확장 템플릿 목록을 출력한다.
      처음 실행하면 repo 도구 의존성(packman)을 내려받는다.
사용법: .\scripts\list_templates.ps1
출력: 화면 + logs/list_templates_<timestamp>.log
#>
. "$PSScriptRoot\_common.ps1"

Invoke-Repo -RepoArgs @("template", "list") -LogPath (New-LogPath "list_templates")
