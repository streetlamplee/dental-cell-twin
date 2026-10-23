<#
목적: config/cad_assets.json에 적힌 CAD 자산 전체를 USD converter로 다시 변환하고, 자산마다 품질 리포트를 만든다. 밀링기는 URDF 대비 검증도 한다.
사용법: .\scripts\convert_all_cad.ps1 [-Name dental_crown]
인자: -Name  자산 하나만 변환 (기본: 전체)
출력: 자산별 USD, <USD>.convert.json, <USD>.report.json, assets/cad/teeth_mill.verify.json, 화면 요약
다음 단계: 제품 변형 레이어는 .\scripts\make_part_variants.ps1 -Part kfl08 / crown 으로 다시 만든다.
#>
param(
    [string]$Name = ""
)
. "$PSScriptRoot\_common.ps1"

$assets = (Get-Content (Join-Path $Root "config\cad_assets.json") -Raw -Encoding utf8 | ConvertFrom-Json).assets
if ($Name) { $assets = @($assets | Where-Object { $_.name -eq $Name }) }
if (-not $assets) { throw "No asset named '$Name' in config/cad_assets.json" }
foreach ($a in $assets) {
    Write-Host "=== $($a.name): profile $($a.profile), tessLOD $($a.tessLOD)"
    $step = Join-Path $Root $a.step
    $usd = Join-Path $Root $a.usd
    & (Join-Path $PSScriptRoot "convert_step_to_usd.ps1") -Stp $step -Out $usd -Profile $a.profile -TessLOD "$($a.tessLOD)" | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0) { throw "conversion failed: $($a.name)" }
    & (Join-Path $PSScriptRoot "report_cad_usd.ps1") -Usd $usd -Step $step
    if ($a.verify_urdf) {
        & (Join-Path $PSScriptRoot "verify_cad_usd.ps1") -Name $a.name | Select-Object -Last 2
        if ($LASTEXITCODE -ne 0) { throw "URDF verification failed: $($a.name)" }
    }
}
