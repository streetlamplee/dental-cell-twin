<#
목적: NVIDIA kit-app-template을 이 프로젝트 루트에 받아온다 (최초 1회).
      프로젝트 루트를 git 저장소로 만들고 upstream 릴리스 브랜치를 체크아웃한다.
사용법: .\scripts\setup_kit_template.ps1 [-Branch 110.4.0]
출력: 프로젝트 루트에 템플릿 파일, git remote 'upstream'
#>
param(
    [string]$Branch = "110.4.0"
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Upstream = "https://github.com/NVIDIA-Omniverse/kit-app-template.git"

Push-Location $Root
try {
    if (Test-Path (Join-Path $Root "repo.toml")) {
        Write-Host "repo.toml already exists. Template is already set up. Nothing to do."
        exit 0
    }

    # 템플릿과 이름이 겹치는 빈 파일은 체크아웃을 막으므로 제거 (내용이 있으면 중단)
    $readme = Join-Path $Root "README.md"
    if ((Test-Path $readme) -and ((Get-Item $readme).Length -gt 0)) {
        throw "README.md has content. Move it aside before setting up the template."
    }
    if (Test-Path $readme) { Remove-Item $readme }

    if (-not (Test-Path (Join-Path $Root ".git"))) {
        git init -b main
        if ($LASTEXITCODE -ne 0) { throw "git init failed" }
    }
    git remote add upstream $Upstream 2>$null
    git fetch --depth 1 upstream $Branch
    if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }

    git checkout -B main FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw "git checkout failed" }

    Write-Host "kit-app-template $Branch checked out at $Root"
}
finally {
    Pop-Location
}
