<#
목적: STEP 파일의 어셈블리 구조(이름, 솔리드 수, 색, 크기)를 출력한다. 부품 선택과 결함 변형 계획에 쓴다. (.venv-cad 필요)
사용법: .\scripts\inspect_step.ps1 -Path assets\parts\raw\kfl08.step   (와일드카드 가능)
출력: 화면 + logs/inspect_step_<timestamp>.log
#>
param(
    [Parameter(Mandatory = $true)][string]$Path
)
. "$PSScriptRoot\_common.ps1"

$py = Join-Path $Root ".venv-cad\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "CAD environment missing. Run .\scripts\setup_cad_env.ps1 first." }
$files = @(Get-ChildItem $Path | ForEach-Object { $_.FullName })
$log = New-LogPath "inspect_step"
$ErrorActionPreference = 'Continue'
& $py (Join-Path $PSScriptRoot "inspect_step.py") @files 2>&1 | ForEach-Object {
    if ($_ -notmatch 'cannot open font') { $_ }
    Add-Content -Path $log -Value $_ -Encoding utf8
}
exit $LASTEXITCODE
