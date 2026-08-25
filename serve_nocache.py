#!/usr/bin/env python3
"""Simple HTTP server with no-cache headers for stockSurface dev."""
from pathlib import Path
import os
BASE_DIR = str(Path(__file__).resolve().parent)

import http.server
import socketserver

PORT = 8765
DIR = BASE_DIR

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, format, *args):
        pass  # quiet

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("0.0.0.0", PORT), NoCacheHandler) as httpd:
    print(f"Serving {DIR} on port {PORT} (no-cache)")
    httpd.serve_forever()
