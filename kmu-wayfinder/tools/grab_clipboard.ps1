# 클립보드에 이미지가 있으면 assets/campusmap.png 로 저장합니다.
# 사용법: powershell -ExecutionPolicy Bypass -File tools\grab_clipboard.ps1
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$dest = Join-Path $PSScriptRoot "..\assets\campusmap.png"
$destDir = Split-Path $dest -Parent
if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Force -Path $destDir | Out-Null }

if ([System.Windows.Forms.Clipboard]::ContainsImage()) {
    $img = [System.Windows.Forms.Clipboard]::GetImage()
    $img.Save($dest, [System.Drawing.Imaging.ImageFormat]::Png)
    $img.Dispose()
    $info = Get-Item $dest
    "SAVED $($info.FullName) ($([int]($info.Length/1KB)) KB)"
} else {
    "NO_IMAGE_IN_CLIPBOARD"
}
