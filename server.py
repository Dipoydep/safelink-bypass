#!/usr/bin/env python3
"""
HTTP Server lokal — jalan di Termux, akses dari browser HP.
Usage: python server.py
Buka: http://localhost:8080
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import sys

from bypass import bypass_safelink


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/" or parsed.path == "/api/bypass":
            target = params.get("url", [None])[0]

            if not target:
                self._html_form()
                return

            try:
                result = bypass_safelink(target, verbose=False)
                self._json(200, result)
            except Exception as e:
                import traceback
                self._json(500, {
                    "success": False,
                    "error": str(e),
                    "trace": traceback.format_exc(),
                })
        else:
            self._json(404, {"error": "Not found"})

    def _json(self, code, data):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_form(self):
        html = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Safelink Bypass</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:#0a0a0a;color:#e0e0e0;padding:20px;max-width:600px;margin:auto;min-height:100vh}
h2{font-size:20px;margin-bottom:16px;display:flex;align-items:center;gap:10px;color:#fff}
h2 svg{flex-shrink:0}
input,button{width:100%;padding:14px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#1a1a1a;color:#fff;font-size:15px;font-family:inherit}
input:focus{outline:none;border-color:#2563eb}
button{background:#2563eb;border:none;font-weight:bold;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:8px;transition:background 0.15s}
button:active{background:#1d4ed8}
button:disabled{background:#333;cursor:wait}
.url-box{background:#0f172a;border:1px solid #1e40af;padding:14px;border-radius:10px;margin:12px 0;word-break:break-all}
.url-box a{color:#60a5fa;text-decoration:none;font-weight:500}
.url-box a:hover{text-decoration:underline}
.meta{color:#888;font-size:12px;margin-bottom:6px;display:flex;align-items:center;gap:6px}
pre.err{background:#1a0a0a;border:1px solid #7f1d1d;color:#f87171;padding:14px;border-radius:10px;font-size:12px;white-space:pre-wrap;word-break:break-all;margin-top:12px}
</style>
</head>
<body>
<h2>
  <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#4ade80" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
    <path d="M7 11V7a5 5 0 0 1 9.9-1"></path>
  </svg>
  Safelink Bypass
</h2>

<input id="url" placeholder="https://sfl.gl/xxxxx" autocomplete="off" autocapitalize="off" spellcheck="false">
<button id="btn" onclick="run()">
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"></path>
  </svg>
  Bypass
</button>

<div id="out"></div>

<script>
const ICON_BOLT = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"></path></svg>';
const ICON_SPIN = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-dasharray="31.4 31.4"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite"/></circle></svg>';
const ICON_LINK = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>';
const ICON_OPEN = '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>';
const ICON_CHECK = '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#4ade80" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';

async function run(){
  const u = document.getElementById('url').value.trim();
  const o = document.getElementById('out');
  const b = document.getElementById('btn');
  if(!u) return;

  b.disabled = true;
  b.innerHTML = ICON_SPIN + ' Memproses...';
  o.innerHTML = '';

  try{
    const r = await fetch('/api/bypass?url=' + encodeURIComponent(u));
    const j = await r.json();

    if(j.success){
      o.innerHTML =
        '<div class="url-box">' +
          '<div class="meta">' + ICON_CHECK + ' ' + (j.method || 'success') + '</div>' +
          '<a href="' + j.url + '" target="_blank">' + j.url + ' ' + ICON_OPEN + '</a>' +
        '</div>';
    } else {
      o.innerHTML = '<pre class="err">✗ ' + (j.error || 'Gagal') + '\\n\\n' + JSON.stringify(j, null, 2) + '</pre>';
    }
  } catch(e){
    o.innerHTML = '<pre class="err">Error: ' + e.message + '</pre>';
  } finally {
    b.disabled = false;
    b.innerHTML = ICON_BOLT + ' Bypass';
  }
}

document.getElementById('url').addEventListener('keydown', e => { if(e.key === 'Enter') run(); });
</script>
</body>
</html>"""
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def main():
    port = 8080
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"[OK] Server jalan di http://localhost:{port}")
    print(f"[OK] Buka browser HP -> http://localhost:{port}")
    print(f"[OK] Ctrl+C buat stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Server stop")
        server.shutdown()


if __name__ == "__main__":
    main()
