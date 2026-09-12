using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading;

// Runs the bundled yt-dlp. If aria2c fails, retries once using yt-dlp's native downloader.
static class YtDlpFallbackLauncher {
    static readonly string Core = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "yt-dlp-core.exe");
    static readonly Regex AriaProgress = new Regex(
        @"^\[#\S+\s+\S+?/(?<total>\S+?)\((?<percent>\d+)%\).*?\bDL:(?<speed>\S+)(?:\s+ETA:(?<eta>\S+))?.*\]$",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);
    static readonly object ConsoleLock = new object();

    static string Quote(string value) {
        if (value.Length == 0) return "\"\"";
        if (!value.Any(c => char.IsWhiteSpace(c) || c == '\"')) return value;
        var result = new System.Text.StringBuilder("\"");
        int backslashes = 0;
        foreach (char character in value) {
            if (character == '\\') { backslashes++; continue; }
            if (character == '\"') result.Append('\\', backslashes * 2 + 1);
            else result.Append('\\', backslashes);
            result.Append(character);
            backslashes = 0;
        }
        result.Append('\\', backslashes * 2);
        return result.Append('\"').ToString();
    }

    static string NormalizeEta(string value) {
        if (String.IsNullOrEmpty(value)) return "-";
        var match = Regex.Match(value, @"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$");
        if (!match.Success) return value;
        int hours = match.Groups[1].Success ? Int32.Parse(match.Groups[1].Value) : 0;
        int minutes = match.Groups[2].Success ? Int32.Parse(match.Groups[2].Value) : 0;
        int seconds = match.Groups[3].Success ? Int32.Parse(match.Groups[3].Value) : 0;
        return String.Format("{0:00}:{1:00}:{2:00}", hours, minutes, seconds);
    }

    static string TranslateAriaProgress(string line) {
        var match = AriaProgress.Match(line.Trim());
        if (!match.Success) return null;
        string speed = match.Groups["speed"].Value;
        if (!speed.EndsWith("/s", StringComparison.OrdinalIgnoreCase)) speed += "/s";
        return String.Format("[download] {0}% of {1} at {2} ETA {3}",
            match.Groups["percent"].Value, match.Groups["total"].Value, speed,
            NormalizeEta(match.Groups["eta"].Value));
    }

    static void Relay(string line, bool stderr, bool translateAria) {
        string translated = translateAria ? TranslateAriaProgress(line) : null;
        lock (ConsoleLock) {
            if (translated != null) Console.Out.WriteLine(translated);
            else if (stderr) Console.Error.WriteLine(line);
            else Console.Out.WriteLine(line);
        }
    }

    static int Run(IEnumerable<string> args, bool translateAria) {
        using (var stdoutDone = new ManualResetEvent(false))
        using (var stderrDone = new ManualResetEvent(false)) {
            var process = new Process { StartInfo = new ProcessStartInfo {
            FileName = Core,
            Arguments = string.Join(" ", args.Select(Quote)),
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        }};
            process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e) {
                if (e.Data == null) stdoutDone.Set(); else Relay(e.Data, false, translateAria);
            };
            process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e) {
                if (e.Data == null) stderrDone.Set(); else Relay(e.Data, true, translateAria);
            };
            process.Start();
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            process.WaitForExit();
            stdoutDone.WaitOne();
            stderrDone.WaitOne();
            int exitCode = process.ExitCode;
            process.Dispose();
            return exitCode;
        }
    }

    static List<string> NativeArguments(string[] args) {
        var result = new List<string>();
        for (int index = 0; index < args.Length; index++) {
            string argument = args[index];
            if (argument == "--downloader" || argument == "--external-downloader" || argument == "--downloader-args" || argument == "--external-downloader-args") {
                index++;
                continue;
            }
            if (argument.StartsWith("--downloader=") || argument.StartsWith("--external-downloader=") || argument.StartsWith("--downloader-args=") || argument.StartsWith("--external-downloader-args=")) continue;
            result.Add(argument);
        }
        result.Add("--downloader");
        result.Add("native");
        return result;
    }

    static int Main(string[] args) {
        if (!File.Exists(Core)) {
            Console.Error.WriteLine("yt-dlp-core.exe is missing. Restore it beside this launcher.");
            return 127;
        }
        bool usesAria2 = args.Any(arg => arg.IndexOf("aria2", StringComparison.OrdinalIgnoreCase) >= 0);
        int firstExit = Run(args, usesAria2);
        if (firstExit == 0 || !usesAria2) return firstExit;
        Console.Error.WriteLine("[speed-fallback] aria2c download failed; retrying once with yt-dlp native downloader.");
        return Run(NativeArguments(args), false);
    }
}
