<#
목적: 합성 데이터(generate_dataset 결과)로 검사 셀의 다중 시점(MIL) CNN을 학습하고 ONNX + 모델 카드로 내보낸다(시스템 Python, PyTorch).
사용법: .\scripts\train_inspector_model.ps1 -Dataset datasets\crown_sdg_v1 [-Name crown_mil] [-Epochs 20]
인자: -Dataset  데이터셋 폴더, -Name  모델 이름(config/models/<Name>.onnx/.json), -Epochs  학습 epoch 수
출력: config/models/<Name>.onnx, config/models/<Name>.json, results/models/<Name>/train_report.json, fig_training.png, logs/train_inspector_model_<timestamp>.log
#>
param(
    [Parameter(Mandatory = $true)][string]$Dataset,
    [string]$Name = "crown_mil",
    [int]$Epochs = 20
)
. "$PSScriptRoot\_common.ps1"

$log = New-LogPath "train_inspector_model"
$out = Join-Path $Root "config\models\$Name"
$report = Join-Path $Root "results\models\$Name"
$ErrorActionPreference = 'Continue'
& python (Join-Path $PSScriptRoot "train_inspector_model.py") (Resolve-Path $Dataset).Path $out $report $Epochs 2>&1 | ForEach-Object {
    $_; Add-Content -Path $log -Value $_ -Encoding utf8
}
exit $LASTEXITCODE
