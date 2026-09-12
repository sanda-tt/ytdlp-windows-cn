# yt-dlp Windows 中文下载器

一个可携带的 Windows 视频下载器：保留 yt-dlg 的中文界面，在其上增加清晰度启动入口、网页视频流兜底解析，以及按媒体类型选择的下载加速。

## 下载与使用

到 GitHub 的 **Releases** 下载 `ytdlp-windows-cn-1.0.1.zip`，解压后双击 `启动下载器.exe`：选择清晰度，然后在打开的中文界面粘贴网页地址、点击“增加”、再开始下载。

发布包不依赖系统安装的 Python、FFmpeg 或 aria2。所有配置保存在包内的 `data` 文件夹，视频默认保存到包内的 `Downloads` 文件夹；移动整个文件夹后，再从 `启动下载器.exe` 打开即可更新路径。

## 功能

- 中文 yt-dlg 图形界面与清晰度选择。
- 普通 HTTP 媒体使用 aria2 多连接下载；HLS/DASH 保持 yt-dlp 原生分片下载。
- aria2 出错时自动回退到 yt-dlp 原生下载器。
- 成功任务中的非致命 yt-dlp 提示不会再被 yt-dlg 误标为 Warning；最终失败仍显示 Error。
- 对原生 yt-dlp 不支持的普通网页，静态提取 video/source、播放器配置、同源脚本和 iframe 中的 m3u8、MPD 或直接媒体地址，再交回 yt-dlp 下载。
- FFmpeg 自动合并分离的音视频流。

## 限制

仅下载你有权保存的内容。受 DRM、登录、验证码、复杂动态接口或访问限制保护的站点可能无法解析或下载。网页兜底解析不执行网页 JavaScript，也不会绕过这些限制。

## 从源码构建

源码仓库不提交第三方二进制文件。将已获取的第三方运行文件放到 `third_party`，布局与发布包一致（包括 `yt-dlg.exe` 和 `tools`），然后运行 `scripts/build-portable.ps1`。脚本使用 Windows .NET Framework C# 编译器生成两个启动器，并输出干净的便携文件夹。

第三方组件与许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
