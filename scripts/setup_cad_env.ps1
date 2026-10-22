<#
목적: STP 생성용 Python 환경(.venv-cad, CadQuery/OpenCascade)을 만든다. 시스템 Python은 건드리지 않는다.
사용법: .\scripts\setup_cad_env.ps1
출력: .venv-cad/ (git 제외), logs/setup_cad_env_<timestamp>.log
#>
. "$PSScriptRoot\_common.ps1"

$venv = Join-Path $Root ".venv-cad"
$req = Join-Path $PSScriptRoot "requirements-cad.txt"
$log = New-LogPath "setup_cad_env"
$ErrorActionPreference = 'Continue'

if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    & python -m venv $venv 2>&1 | ForEach-Object { $_; Add-Content -Path $log -Value $_ -Encoding utf8 }
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed. Log: $log" }
}
$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install --upgrade pip -q 2>&1 | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding utf8 }
& $py -m pip install -r $req 2>&1 | ForEach-Object { $_; Add-Content -Path $log -Value $_ -Encoding utf8 }
if ($LASTEXITCODE -ne 0) { throw "pip install failed. Log: $log" }
& $py -c "import cadquery, OCP; print('cadquery', cadquery.__version__)" 2>&1 | ForEach-Object { $_; Add-Content -Path $log -Value $_ -Encoding utf8 }
exit $LASTEXITCODE
