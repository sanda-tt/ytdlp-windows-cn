using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;

static class QualityLauncher {
    static readonly string Root = AppDomain.CurrentDomain.BaseDirectory;
    // Keep settings beside the application so the release folder is portable.
    static readonly string AppData = Path.Combine(Root, "data");
    static readonly string Config = Path.Combine(AppData, "yt-dlg", "settings.json");
    static readonly string Preference = Path.Combine(Root, "quality-preference.txt");
    static readonly string[] Labels = { "最高画质（按原视频）", "4K / 2160p", "2K / 1440p", "全高清 / 1080p", "高清 / 720p", "标清 / 480p", "流畅 / 360p" };
    static readonly string[] Resolutions = { "res", "res:2160", "res:1440", "res:1080", "res:720", "res:480", "res:360" };
    static string Sort(int index) { return Resolutions[index] + ",vcodec:h264,acodec:aac"; }
    static int DownloadConcurrency() { return Math.Min(8, Math.Max(4, Environment.ProcessorCount / 2)); }
    static string Arguments(int index) {
        string tools = Path.Combine(Root, "tools").Replace('\\', '/');
        int concurrency = DownloadConcurrency();
        string aria2 = tools + "/aria2/aria2c.exe";
        return "--ffmpeg-location \"" + tools + "\" --js-runtimes \"deno:" + tools + "/deno.exe\" --windows-filenames --merge-output-format mp4"
            + " --concurrent-fragments " + concurrency
            + " --downloader \"" + aria2 + "\" --downloader \"dash,m3u8:native\""
            + " --downloader-args \"aria2c:-x " + concurrency + " -s " + concurrency + " -k 1M --file-allocation=none --summary-interval=1 --console-log-level=warn\""
            + " -S \"" + Sort(index) + "\"";
    }
    static void Apply(int index, bool launch) {
        if (Process.GetProcessesByName("yt-dlp").Length != 0) throw new Exception("检测到下载任务，请完成或停止下载后再改变清晰度。");
        string gui = Path.Combine(Root, "yt-dlg.exe");
        foreach (Process p in Process.GetProcessesByName("yt-dlg")) {
            if (p.MainWindowHandle == IntPtr.Zero || !String.Equals(p.MainModule.FileName, gui, StringComparison.OrdinalIgnoreCase)) continue;
            p.CloseMainWindow();
            if (!p.WaitForExit(5000)) throw new Exception("请关闭已打开的下载器窗口，再点击此按钮。");
        }
        Directory.CreateDirectory(Path.GetDirectoryName(Config));
        if (!File.Exists(Config)) throw new FileNotFoundException("找不到发布包内的默认配置。", Config);
        var json = new JavaScriptSerializer();
        var config = json.Deserialize<System.Collections.Generic.Dictionary<string, object>>(File.ReadAllText(Config));
        config["cmd_args"] = Arguments(index);
        config["locale_name"] = "zh_CN";
        config["youtubedl_path"] = Path.Combine(Root, "tools");
        config["save_path"] = Path.Combine(Root, "Downloads");
        config["selected_format"] = "0";
        config["video_format"] = "0";
        config["to_audio"] = false;
        config["confirm_exit"] = false;
        config["workers_number"] = 1;
        config["ignore_errors"] = false;
        config["retries"] = 5;
        File.WriteAllText(Config, json.Serialize(config), new UTF8Encoding(false));
        File.WriteAllText(Preference, Sort(index));
        if (launch) {
            var start = new ProcessStartInfo(gui) { WorkingDirectory = Root };
            start.EnvironmentVariables["APPDATA"] = AppData;
            start.EnvironmentVariables["LOCALAPPDATA"] = AppData;
            Process.Start(start);
        }
    }
    [STAThread]
    static int Main(string[] args) {
        if (args.Length == 2 && args[0] == "--apply") {
            try { Apply(Array.IndexOf(Resolutions, args[1]), false); return 0; }
            catch { return 1; }
        }
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        var form = new Form { Text = "视频下载器 - 选择清晰度", ClientSize = new Size(540, 300), StartPosition = FormStartPosition.CenterScreen, FormBorderStyle = FormBorderStyle.FixedDialog, MaximizeBox = false, Font = new Font("Microsoft YaHei UI", 10) };
        var heading = new Label { Text = "选择下载清晰度", Location = new Point(25, 20), AutoSize = true };
        var combo = new ComboBox { Location = new Point(25, 57), Size = new Size(490, 32), DropDownStyle = ComboBoxStyle.DropDownList, AccessibleName = "下载清晰度" };
        combo.Items.AddRange(Labels);
        combo.SelectedIndex = 0;
        if (File.Exists(Preference)) {
            string saved = File.ReadAllText(Preference).Trim();
            for (int i = 0; i < Labels.Length; i++) if (saved == Sort(i)) combo.SelectedIndex = i;
        }
        var help = new Label { Text = "按网站实际提供的画质选择，不会把低清视频放大。\r\n自动加速已开启：普通文件多连接，HLS/DASH 使用并发分片。\r\n选好后：粘贴链接 → 增加 → 右下角开始下载。\r\n改变清晰度会重开下载器，请先完成当前任务。", Location = new Point(25, 108), Size = new Size(490, 110) };
        var start = new Button { Text = "应用并打开下载器", Location = new Point(300, 241), Size = new Size(215, 37) };
        start.Click += delegate {
            try { Apply(combo.SelectedIndex, true); form.Close(); }
            catch (Exception ex) { MessageBox.Show(form, ex.Message, "无法应用配置", MessageBoxButtons.OK, MessageBoxIcon.Information); }
        };
        form.Controls.AddRange(new Control[] { heading, combo, help, start });
        form.AcceptButton = start;
        Application.Run(form);
        return 0;
    }
}
