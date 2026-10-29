<#
목적: 런타임 변경 전 Extension·캡처 소스와 해시를 보존해 수정 전 수명주기 재현에 사용.
사용법: .\scripts\snapshot_interview_source.ps1
출력: results/interview/source_before/<timestamp>/의 소스와 snapshot.json.
#>
. "$PSScriptRoot\_common.ps1"
$out = Join-Path $Root "results\interview\source_before\$(Get-Date -Format yyyyMMdd_HHmmss)"
New-Item -ItemType Directory -Path $out -Force | Out-Null
$files = @()
foreach ($name in @('extension.py','frame_provider.py')) {
    $source = Join-Path $Root "source\extensions\visiontwin.factory\visiontwin\factory\$name"
    Copy-Item -LiteralPath $source -Destination (Join-Path $out $name)
    $files += @{name=$name; sha256=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash}
}
@{commit=(& git -C $Root rev-parse HEAD); files=$files} | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $out 'snapshot.json') -Encoding utf8
Write-Host "Source snapshot: $out"
