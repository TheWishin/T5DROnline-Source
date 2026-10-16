# Capture the game window to PNG.
#   powershell -File tools\screenshot.ps1 [-Out build\shot.png] [-ProcessId N] [-Count 1] [-IntervalMs 100]
# With -Count > 1 it writes <Out base>_00.png, _01.png, ... (a burst, to catch
# flashing frames). Brings the window to the front first; the capture is of
# the screen area the window covers, so nothing may overlap it.
param([string]$Out = "build\shot.png", [int]$ProcessId = 0, [int]$Count = 1, [int]$IntervalMs = 100)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[Win]::SetProcessDPIAware() | Out-Null
$procs = Get-Process t5dr -ErrorAction Stop | Where-Object { $_.MainWindowHandle -ne 0 }
if ($ProcessId) { $procs = $procs | Where-Object { $_.Id -eq $ProcessId } }
$p = $procs | Select-Object -First 1
if (-not $p) { throw "no t5dr.exe window" }
$h = $p.MainWindowHandle
[Win]::ShowWindow($h, 9) | Out-Null
[Win]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 400
$r = New-Object Win+RECT
[Win]::GetWindowRect($h, [ref]$r) | Out-Null
$w = $r.R - $r.L; $hgt = $r.B - $r.T
$base = [System.IO.Path]::Combine([System.IO.Path]::GetDirectoryName($Out), [System.IO.Path]::GetFileNameWithoutExtension($Out))
for ($i = 0; $i -lt $Count; $i++) {
    $bmp = New-Object System.Drawing.Bitmap $w, $hgt
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size)
    $file = if ($Count -gt 1) { "{0}_{1:D2}.png" -f $base, $i } else { $Out }
    $bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    if ($Count -gt 1) { Start-Sleep -Milliseconds $IntervalMs }
}
"saved $Count frame(s) of $w x $hgt from pid $($p.Id)"
