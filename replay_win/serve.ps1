$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$port = 8791
while ($true) {
  $busy = Test-NetConnection -ComputerName 127.0.0.1 -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue
  if (-not $busy) { break }
  $port++
}
Write-Host "Replay starting: http://127.0.0.1:$port/index.html" -ForegroundColor Cyan

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
      if ((Test-Path $fp -PathType Leaf) -and ((Resolve-Path $fp).Path.StartsWith($r.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase))) {
        $ext = [IO.Path]::GetExtension($fp).TrimStart('.')
        $bytes = [IO.File]::ReadAllBytes($fp)
        if ($ext -eq 'gz') { $ctx.Response.Headers['Content-Encoding'] = 'gzip' }
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
Write-Host "Browser opened. Keep this window open to keep the server running." -ForegroundColor Yellow
Write-Host "Archives are stored in this browser localStorage." 
Write-Host ""
try { Wait-Event -Timeout ([int]::MaxValue) } catch {}
Stop-Job $job -ErrorAction SilentlyContinue
Remove-Job $job -Force -ErrorAction SilentlyContinue
