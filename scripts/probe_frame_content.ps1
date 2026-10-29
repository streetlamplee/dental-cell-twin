<#
목적: 진단 전용 이진 마커로 캡처 프레임 번호와 실제 이미지 내용의 대응을 측정.
사용법: .\scripts\probe_frame_content.ps1
출력: results/interview/frame_content/<timestamp>/report.json 및 진단 이미지.
#>
. "$PSScriptRoot\_interview.ps1"
$out = Join-Path $Root "results\interview\frame_content\$(Get-Date -Format yyyyMMdd_HHmmss)"
Invoke-InterviewKit -Script 'probe_frame_content.py' -Out $out -TimeoutSeconds 240 -Settings @{'/exts/visiontwin.factory/vision'='false'}
