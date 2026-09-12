param(
    [string]$DependencyRoot = (Join-Path $PSScriptRoot '..\third_party'),
    [string]$OutputRoot = (Join-Path $PSScriptRoot '..\dist\ytdlp-windows-cn')
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$compiler = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw '需要 Windows .NET Framework C# 编译器。' }
if (-not (Test-Path -LiteralPath (Join-Path $DependencyRoot 'yt-dlg.exe'))) { throw 'third_party 中缺少 yt-dlg.exe。' }
if (Test-Path -LiteralPath $OutputRoot) { Remove-Item -LiteralPath $OutputRoot -Recurse -Force }

New-Item -ItemType Directory -Path $OutputRoot, (Join-Path $OutputRoot 'tools'), (Join-Path $OutputRoot 'data\yt-dlg'), (Join-Path $OutputRoot 'Downloads') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $DependencyRoot 'yt-dlg.exe') -Destination $OutputRoot
Copy-Item -Path (Join-Path $DependencyRoot 'tools\*') -Destination (Join-Path $OutputRoot 'tools') -Recurse
Copy-Item -LiteralPath (Join-Path $projectRoot 'plugins\webstream') -Destination (Join-Path $OutputRoot 'tools\yt-dlp-plugins') -Recurse -Force

$launcherOutput = '/out:' + (Join-Path $OutputRoot '启动下载器.exe')
$wrapperOutput = '/out:' + (Join-Path $OutputRoot 'tools\yt-dlp.exe')
& $compiler /nologo /target:winexe $launcherOutput /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Web.Extensions.dll (Join-Path $projectRoot 'src\QualityLauncher.cs')
& $compiler /nologo /target:exe $wrapperOutput (Join-Path $projectRoot 'src\YtDlpFallbackLauncher.cs')

$tools = (Join-Path $OutputRoot 'tools').Replace('\', '/')
$settings = [ordered]@{
    save_path = (Join-Path $OutputRoot 'Downloads'); save_path_dirs = @((Join-Path $OutputRoot 'Downloads'))
    locale_name = 'zh_CN'; youtubedl_path = (Join-Path $OutputRoot 'tools'); cli_backend = 'yt-dlp.exe'
    output_template = '%(uploader)s\%(title)s.%(ext)s'; selected_format = '0'; video_format = '0'
    workers_number = 1; ignore_errors = $false; retries = 5; native_hls = $true; ignore_config = $true
    cmd_args = "--ffmpeg-location `"$tools`" --js-runtimes `"deno:$tools/deno.exe`" --windows-filenames --merge-output-format mp4 --concurrent-fragments 8 --downloader `"$tools/aria2/aria2c.exe`" --downloader `"dash,m3u8:native`" --downloader-args `"aria2c:-x 8 -s 8 -k 1M --file-allocation=none --summary-interval=1 --console-log-level=warn`" -S `"res,vcodec:h264,acodec:aac`""
}
$settings | ConvertTo-Json -Depth 5 -Compress | Set-Content -LiteralPath (Join-Path $OutputRoot 'data\yt-dlg\settings.json') -Encoding utf8NoBOM
Copy-Item -LiteralPath (Join-Path $projectRoot 'LICENSE'), (Join-Path $projectRoot 'THIRD_PARTY_NOTICES.md') -Destination $OutputRoot
