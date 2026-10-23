<#
목적: STEP 1개를 USD converter 테셀레이션 LOD 0~4로 각각 변환하고, 품질 리포트(삼각형 수, B-rep 대비 부피/면적 오차, 파일 크기, 변환 시간)를 비교한다. 자산별 LOD를 고르는 근거.
사용법: .\scripts\compare_tess_lod.ps1 -Stp assets\parts\raw\dental_crown.step
인자: -Stp  비교할 STEP (프로파일은 product, LOD만 바꾼다)
출력: results/cad_lod/<이름>/lod<n>.usd(+ .convert.json, .report.json; USD는 git 제외), results/cad_lod/<이름>/table.md, results/cad_lod/lod_compare.png(전체 자산)
#>
param(
    [Parameter(Mandatory = $true)][string]$Stp
)
. "$PSScriptRoot\_common.ps1"

$name = [IO.Path]::GetFileNameWithoutExtension($Stp)
$outDir = Join-Path $Root "results\cad_lod\$name"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
foreach ($lod in 0..4) {
    $usd = Join-Path $outDir "lod$lod.usd"
    & (Join-Path $PSScriptRoot "convert_step_to_usd.ps1") -Stp $Stp -Out $usd -Profile product -TessLOD $lod | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0) { throw "conversion failed at LOD $lod" }
    & (Join-Path $PSScriptRoot "report_cad_usd.ps1") -Usd $usd -Step $Stp
}
& python (Join-Path $PSScriptRoot "summarize_tess_lod.py") (Join-Path $Root "results\cad_lod")
exit $LASTEXITCODE
