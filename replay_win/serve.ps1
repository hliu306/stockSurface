# ═══════════════════════════════════════════════════════
#  行业轮动 Replay — Windows 启动器
#  双击 启动.bat 即可: 起本地服务 + 自动打开浏览器
#  关闭: 直接关掉弹出的黑窗口
# ═══════════════════════════════════════════════════════
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$port = 8791
# 端口被占则换一个
while ($true) {
  $busy = Test-NetConnection -ComputerName 127.0.0.1 -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue
  if (-not $busy) { break }
  $port++
}
Write-Host "replay 服务启动中: http://127.0.0.1:$port/index.html" -ForegroundColor Cyan

# 起 HTTP 服务(仅本机可见)
$job = Start-Job -ScriptBlock {
  param($p, $r)
  $H = New-Object System.Net.HttpListener
  $H.Prefixes.Add("http://127.0.0.1:$p/")
  $H.Start()
  $types = @{'html'='text/html; charset=utf-8'; 'json'='application/json'; 'gz'='application/json'; 'js'='text/javascript'; 'css'='text/css'}
  while ($H.IsListening) {
    $ctx = $H.GetContext()
    try {
      $rel = [Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath).TrimStart('/')
      if ($rel -eq '') { $rel = 'index.html' }
      $fp = Join-Path $r $rel
      if ((Test-Path $fp -PathType Leaf) -and ((Resolve-Path $fp).Path.StartsWith($r))) {
        $ext = [IO.Path]::GetExtension($fp).TrimStart('.')
        $bytes = [IO.File]::ReadAllBytes($fp)
        if ($ext -eq 'gz') { $ctx.Response.Headers['Content-Encoding'] = 'gzip' }  # 让浏览器原生解压
        $ctx.Response.ContentType = if ($types.ContainsKey($ext)) { $types[$ext] } else { 'application/octet-stream' }
        $ctx.Response.Headers['Cache-Control'] = 'no-store'
        $ctx.Response.ContentLength64 = $bytes.Length
        $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
      } else {
        $ctx.Response.StatusCode = 404
      }
    } catch { try { $ctx.Response.StatusCode = 500 } catch {} }
    finally { try { $ctx.Response.OutputStream.Close() } catch {} }
  }
} -ArgumentList $port, $root

Start-Sleep -Milliseconds 800
Start-Process "http://127.0.0.1:$port/index.html"
Write-Host ""
Write-Host "已打开浏览器. 保持此窗口开着; 关闭此窗口=停止服务." -ForegroundColor Yellow
Write-Host "交易存档保存在浏览器 localStorage(本机本浏览器)." 
Write-Host ""
try { Wait-Event -Timeout ([int]::MaxValue) } catch {}
Stop-Job $job -ErrorAction SilentlyContinue
Remove-Job $job -Force -ErrorAction SilentlyContinue
