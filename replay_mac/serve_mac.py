#!/usr/bin/env python3
"""mac版启动器: 静态文件服务, gz带Content-Encoding(老Safari原生解压), 自动开浏览器, 端口自延"""
import http.server, socketserver, os, sys, webbrowser, threading

PORT = 8791
ROOT = os.path.dirname(os.path.abspath(__file__))

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()
    def translate_path(self, path):
        p = super().translate_path(path)
        # 路径穿越防护
        rp = os.path.realpath(p)
        if not rp.startswith(os.path.realpath(ROOT)):
            return os.path.join(ROOT, 'nonexistent')
        return p
    def guess_type(self, path):
        if path.endswith('.gz'):
            return 'application/json'
        return super().guess_type(path)
    def do_GET(self):
        p = self.translate_path(self.path)
        if self.path.split('?')[0].endswith('.gz') and os.path.exists(p):
            with open(p, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Encoding', 'gzip')   # 关键: 浏览器原生解压(老Safari兼容)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            super().do_GET()

def find_port():
    import socket
    global PORT
    while True:
        with socket.socket() as s:
            try:
                s.bind(('127.0.0.1', PORT)); return PORT
            except OSError:
                PORT += 1

if __name__ == '__main__':
    port = find_port()
    url = f'http://127.0.0.1:{port}/index.html'
    print(f'replay 服务: {url}')
    print('保持此窗口开着; Ctrl+C 或关闭窗口=停止')
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(('127.0.0.1', port), H)
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
