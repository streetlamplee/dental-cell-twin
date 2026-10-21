<#
목적: 모든 스크립트가 dot-source 하는 공통 헬퍼. 직접 실행하지 않는다.
사용법: . "$PSScriptRoot\_common.ps1"
제공: $Root(프로젝트 루트), $LogDir, Invoke-Repo, New-LogPath
#>
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# PATH에 빈 항목(';;' 또는 맨 앞 ';')이 있으면 cmd.exe가 명령을 찾지 못한다.
# repo.bat / packman은 cmd를 거치므로 빈 항목을 제거한다. (docs: [[cmd PATH 빈 항목 문제]])
$env:Path = (($env:Path -split ';') | Where-Object { $_.Trim() -ne '' }) -join ';'

# Kit flags for unattended runs (--exec scripts): no crash-report dialog, no save prompt on quit.
$KitAutomationArgs = "--/crashreporter/gatherUserStory=0 --/app/file/ignoreUnsavedOnExit=true"

# Two Kit instances sharing the 8 GB GPU coincided with D3D crashes when the inspection
# viewport was created (docs: [[검사 카메라 프레임 캡처 (Gate B)]]). Warn, do not block.
if (Get-Process kit -ErrorAction SilentlyContinue) {
    Write-Warning "Another kit.exe is running. Close it for stable automated runs (shared GPU memory)."
}

function New-LogPath([string]$Name) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    return Join-Path $LogDir "${Name}_${stamp}.log"
}

# repo.bat 실행. 출력은 화면과 로그 파일에 같이 남기고, 실패하면 예외를 던진다.
function Invoke-Repo([string[]]$RepoArgs, [string]$LogPath) {
    Push-Location $Root
    try {
        # 네이티브 stderr가 ErrorRecord로 바뀌어 Stop 되는 것을 막는다 (PS 5.1)
        $prev = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        # Tee-Object는 PS 5.1에서 UTF-16으로 저장하므로 UTF-8로 직접 기록한다
        & cmd /c ".\repo.bat $($RepoArgs -join ' ') 2>&1" | ForEach-Object {
            $_
            Add-Content -Path $LogPath -Value $_ -Encoding utf8
        }
        $code = $LASTEXITCODE
        $ErrorActionPreference = $prev
        if ($code -ne 0) { throw "repo.bat $($RepoArgs -join ' ') failed (exit $code). Log: $LogPath" }
    }
    finally {
        Pop-Location
    }
}
