<#
목적: 치아 밀링 라인용 제품 모델(블랭크, 크라운, 미완성 크라운)을 CadQuery로 만들어 STEP으로 저장한다. (.venv-cad 필요)
사용법: .\scripts\make_dental_parts.ps1
출력: assets/parts/raw/dental_*.step, logs/make_dental_parts_<timestamp>.log
#>
. "$PSScriptRoot\_common.ps1"

$py = Join-Path $Root ".venv-cad\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "CAD environment missing. Run .\scripts\setup_cad_env.ps1 first." }
$log = New-LogPath "make_dental_parts"
$ErrorActionPreference = 'Continue'
& $py (Join-Path $PSScriptRoot "make_dental_parts.py") (Join-Path $Root "assets\parts\raw") 2>&1 | ForEach-Object {
    if ($_ -notmatch 'cannot open font') { $_ }
    Add-Content -Path $log -Value $_ -Encoding utf8
}
exit $LASTEXITCODE
