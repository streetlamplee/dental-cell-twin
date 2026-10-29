<#
목적: 자동 검증 중 Kit 주 창의 최소화·가시성 상태를 읽기 전용으로 기록한다.
사용법: .\scripts\inspect_kit_window.ps1
출력: results/interview/window_<timestamp>.json, logs/inspect_kit_window_<timestamp>.log
#>
. "$PSScriptRoot\_common.ps1"
if (-not ('VisionTwinWindowDiagnostics' -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class VisionTwinWindowDiagnostics {
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@
}
$rows = @(Get-Process kit -ErrorAction SilentlyContinue | ForEach-Object {
    $handle = $_.MainWindowHandle
    @{pid=$_.Id; main_window_handle=$handle.ToInt64(); minimized=[VisionTwinWindowDiagnostics]::IsIconic($handle);
      visible=[VisionTwinWindowDiagnostics]::IsWindowVisible($handle);
      foreground=($handle -eq [VisionTwinWindowDiagnostics]::GetForegroundWindow())}
})
$data = @{observed_utc=[DateTime]::UtcNow.ToString('o'); windows=$rows}
$outputPath = Join-Path $Root "results/interview/window_$(Get-Date -Format yyyyMMdd_HHmmss).json"
$json = $data | ConvertTo-Json -Depth 4
$json | Set-Content -LiteralPath $outputPath -Encoding utf8
$json | Set-Content -LiteralPath (New-LogPath 'inspect_kit_window') -Encoding utf8
Write-Output $json
