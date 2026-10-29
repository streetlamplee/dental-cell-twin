<#
목적: 실험 스크립트 Python/PowerShell 구문과 새 Obsidian 노트 형식·링크 검증.
사용법: .\scripts\check_interview_artifacts.ps1
출력: 화면, logs/check_interview_artifacts_<timestamp>.log. 오류 시 실패.
#>
. "$PSScriptRoot\_common.ps1"
$log = New-LogPath 'check_interview_artifacts'
foreach ($file in (Get-ChildItem $PSScriptRoot -Filter '*.ps1')) {
    $parseTokens = $null
    $parseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$parseTokens, [ref]$parseErrors) | Out-Null
    if ($parseErrors.Count) { throw "$($file.Name): $parseErrors" }
}
& python "$PSScriptRoot\check_interview_artifacts.py" 2>&1 | ForEach-Object { $_; Add-Content $log $_ -Encoding utf8 }
if ($LASTEXITCODE -ne 0) { throw "Artifact checks failed: $log" }
