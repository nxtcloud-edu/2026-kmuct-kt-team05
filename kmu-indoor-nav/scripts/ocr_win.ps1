# Windows 내장 OCR(Windows.Media.Ocr)로 도면 이미지의 텍스트를 추출한다.
# 비전 도구 없이 도면 내부 층 표기를 판독하기 위한 대체 경로.
#
# 사용법:
#   powershell -ExecutionPolicy Bypass -File scripts/ocr_win.ps1 -Path <png> [-Lang ko]
#
# 출력: 인식된 줄 단위 텍스트 (탭 구분: 신뢰도 없음, WinRT OCR 은 줄/단어 단위만 제공)

param(
  [Parameter(Mandatory = $true)][string]$Path,
  [string]$Lang = "ko",
  [double]$Upscale = 2.0
)

$ErrorActionPreference = "Stop"

# 한글 출력이 호출측(파이썬 subprocess 등)에서 깨지지 않도록 UTF-8 로 고정
try {
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null

# WinRT 타입 로드
$null = [Windows.Media.Ocr.OcrEngine, Windows.Media, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]

# IAsyncOperation -> 동기 대기 헬퍼
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await($op, $resultType) {
  $m = $asTaskGeneric.MakeGenericMethod($resultType)
  $task = $m.Invoke($null, @($op))
  $task.Wait(60000) | Out-Null
  return $task.Result
}

$full = (Resolve-Path $Path).Path

# 확대: 작은 글자 인식률을 올리기 위해 임시 파일로 리샘플
$work = $full
if ($Upscale -ne 1.0) {
  Add-Type -AssemblyName System.Drawing
  $src = [System.Drawing.Image]::FromFile($full)
  $w = [int]($src.Width * $Upscale); $h = [int]($src.Height * $Upscale)
  $bmp = New-Object System.Drawing.Bitmap $w, $h
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.DrawImage($src, 0, 0, $w, $h)
  $g.Dispose(); $src.Dispose()
  $work = [System.IO.Path]::Combine($env:TEMP, ("ocr_up_" + [System.IO.Path]::GetFileName($full)))
  $bmp.Save($work, [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
}

$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($work)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$engine = $null
try {
  $language = New-Object Windows.Globalization.Language $Lang
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
} catch { $engine = $null }
if ($null -eq $engine) {
  Write-Output "LANG_UNAVAILABLE: $Lang"
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
}
if ($null -eq $engine) { throw "OCR 엔진을 만들 수 없습니다. 언어팩 확인 필요." }

Write-Output ("ENGINE_LANG: " + $engine.RecognizerLanguage.LanguageTag)

$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

foreach ($line in $result.Lines) {
  $words = @()
  foreach ($wd in $line.Words) {
    $r = $wd.BoundingRect
    $words += ("{0}@{1},{2}" -f $wd.Text, [int]($r.X / $Upscale), [int]($r.Y / $Upscale))
  }
  Write-Output ("LINE`t" + $line.Text + "`t" + ($words -join " "))
}
