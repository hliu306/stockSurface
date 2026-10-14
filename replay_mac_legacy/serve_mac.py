#!/usr/bin/env python3
"""macOS 10.11.6 + Python 3.6.8 + Safari 11 兼容启动器(3.5+语法)"""
import http.server, socketserver, os, sys, webbrowser, threading
try:
    from socketserver import TCPServer
except ImportError:
    from socketserver import TCPServer

PORT = 8791
ROOT = os.path.dirname(os.path.abspath(__file__))

class H(http.server.SimpleHTTPRequestHandler):
    # Python3.6: SimpleHTTPRequestHandler 无 directory 参数 → chdir 方案
    # 3.7+ 的 translate_path 会读 self.directory — 显式提供, 新旧两版行为一致(都指向 ROOT)
    directory = ROOT
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        http.server.SimpleHTTPRequestHandler.end_headers(self)
    def guess_type(self, path):
        if path.endswith('.gz'):
            return 'application/json'
        return http.server.SimpleHTTPRequestHandler.guess_type(self, path)
    def do_GET(self):
        p = self.translate_path(self.path)
        rp = os.path.realpath(p)
        root = os.path.realpath(os.getcwd())   # chdir后 cwd=ROOT
        if not rp.startswith(root + os.sep) and rp != root:
            self.send_error(404)
            return
        if self.path.split('?')[0].endswith('.gz') and os.path.isfile(p):
            with open(p, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Encoding', 'gzip')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            http.server.SimpleHTTPRequestHandler.do_GET(self)

def find_port():
    global PORT
    import socket
    while True:
        s = socket.socket()
        try:
            s.bind(('127.0.0.1', PORT))
            return PORT
        except OSError:
            PORT += 1
        finally:
            s.close()

os.chdir(ROOT)   # 模块加载即定位到脚本目录(3.6无directory=参数)

if __name__ == '__main__':
    port = find_port()
    url = 'http://127.0.0.1:%d/index.html' % port
    print('replay 服务: ' + url)
    print('保持此窗口开着; Ctrl+C 或关闭窗口=停止')
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(('127.0.0.1', port), H)
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
