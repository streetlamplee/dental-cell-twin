<#
목적: 검사 모델 학습(Kit 밖)에 필요한 Python 패키지를 시스템 Python에 설치한다(scripts/requirements-ml.txt).
사용법: .\scripts\setup_ml_env.ps1
출력: 화면(설치 결과, torch CUDA 사용 가능 여부), logs/setup_ml_env_<timestamp>.log
주의: torch는 CUDA 빌드가 필요하다. 없으면 requirements-ml.txt 주석의 --index-url 명령으로 먼저 설치한다.
#>
. "$PSScriptRoot\_common.ps1"

$log = New-LogPath "setup_ml_env"
$ErrorActionPreference = 'Continue'
& python -m pip install -r (Join-Path $PSScriptRoot "requirements-ml.txt") 2>&1 | ForEach-Object {
    Add-Content -Path $log -Value $_ -Encoding utf8
    if ($_ -match 'Successfully|ERROR|already satisfied: (torch|onnx)') { $_ }
}
& python -c "import torch, onnx; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), 'onnx', onnx.__version__)"
exit $LASTEXITCODE
