<#
목적: 실제 CAD 부품의 제품 변형(good / color / missing) USD 레이어를 만든다(원본 변환 USD는 참조만). (.venv-cad 필요)
사용법: .\scripts\make_part_variants.ps1 [-Part kfl08]
인자: -Part  assets/parts/catalog.json의 부품 이름
출력: assets/parts/usd/<Part>_<variant>.usda, logs/make_part_variants_<timestamp>.log
#>
param(
    [string]$Part = "kfl08"
)
. "$PSScriptRoot\_common.ps1"

$py = Join-Path $Root ".venv-cad\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "CAD environment missing. Run .\scripts\setup_cad_env.ps1 first." }
$log = New-LogPath "make_part_variants"
$ErrorActionPreference = 'Continue'
& $py (Join-Path $PSScriptRoot "make_part_variants.py") $Part 2>&1 | ForEach-Object {
    $_; Add-Content -Path $log -Value $_ -Encoding utf8
}
exit $LASTEXITCODE
