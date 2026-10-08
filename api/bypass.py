from http.server import BaseHTTPRequestHandler
import json
import re
import base64
import binascii
import time
import random
from urllib.parse import urlparse, parse_qs, urlencode
import urllib.request
import urllib.error
import http.cookiejar
import ssl

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; SM-S918B) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Referer": "https://www.google.com/",
}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


# ============================================================
# HTTP CLIENT — dengan cookie jar (buat /api/session + /api/go)
# ============================================================
class HttpClient:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=CTX),
        )

    def get(self, url, headers=None, timeout=20):
        h = dict(HEADERS)
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, headers=h)
        try:
            with self.opener.open(req, timeout=timeout) as r:
                return r.status, r.geturl(), r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            return e.code, url, e.read().decode("utf-8", "ignore")
        except Exception as e:
            return 0, url, f"ERROR: {e}"

    def post(self, url, data=None, json_data=None, headers=None, timeout=20):
        h = dict(HEADERS)
        h["Content-Type"] = "application/json"
        if headers:
            h.update(headers)
        if json_data is not None:
            body = json.dumps(json_data).encode()
        elif isinstance(data, dict):
            body = urlencode(data).encode()
        else:
            body = (data or "").encode()
        req = urllib.request.Request(url, data=body, headers=h, method="POST")
        try:
            with self.opener.open(req, timeout=timeout) as r:
                return r.status, r.geturl(), r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            return e.code, url, e.read().decode("utf-8", "ignore")
        except Exception as e:
            return 0, url, f"ERROR: {e}"


# ============================================================
# UTILS
# ============================================================
def b64_decode(s):
    try:
        return base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "ignore")
    except Exception:
        return None


def extract_urls(text):
    return re.findall(r'https?://[^\s"\'<>\\]+', text)


def has_fragment(url):
    return "#" in url


# ============================================================
# CORE: PANGGIL /api/go DARI HALAMAN KHADDAVI
# ============================================================
def try_api_go(html_page_url, client, logs):
    """
    Dari halaman khaddavi, panggil /api/go untuk dapet URL target.
    """
    parsed = urlparse(html_page_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    # 1. POST /api/session — inisialisasi session
    # Butuh _token dari cookie XSRF-TOKEN. Coba pake token dummy + fingerprint
    fingerprint = f"webgl:Google Inc.|audio:0.123456|canvas:abc123|fonts:24/24|system:{random.randint(2,16)}CPU"
    token = f"{int(time.time())}{random.randint(1000000, 9999999)}"

    session_url = f"{base}/api/session"
    st, fu, body = client.post(session_url, json_data={"_token": token})
    logs.append(f"  POST {session_url} -> {st}")

    step = 1
    try:
        j = json.loads(body)
        step = j.get("step", 1)
        logs.append(f"  session step={step}, captcha={j.get('captcha')}")
    except Exception:
        logs.append(f"  session body: {body[:200]}")

    # 2. POST /api/go — ambil URL target
    key = random.randint(1, 999)
    size = f"{random.randint(700, 1400)}.{random.randint(1200, 2200)}"
    go_url = f"{base}/api/go"
    st, fu, body = client.post(go_url, json_data={"key": key, "size": size, "ado": None})
    logs.append(f"  POST {go_url} -> {st}")

    try:
        j = json.loads(body)
        url = j.get("url") or j.get("target") or j.get("link")
        if url:
            logs.append(f"  FINAL (api/go): {url}")
            return url
        logs.append(f"  api/go response: {json.dumps(j)[:200]}")
    except Exception:
        logs.append(f"  api/go body: {body[:200]}")

    # 3. Fallback: POST /api/verify
    verify_url = f"{base}/api/verify"
    st, fu, body = client.post(verify_url, json_data={"_a": 0})
    logs.append(f"  POST {verify_url} -> {st}")
    try:
        j = json.loads(body)
        url = j.get("target") or j.get("url")
        if url:
            logs.append(f"  FINAL (api/verify): {url}")
            return url
    except Exception:
        pass

    return None


def bypass(url, depth=0, max_depth=4, visited=None):
    if visited is None:
        visited = set()

    if url in visited:
        return {"success": False, "error": "Loop detected", "url": url, "logs": []}

    visited.add(url)

    if depth >= max_depth:
        return {"success": False, "error": "Max depth reached", "url": url, "logs": []}

    logs = []
    client = HttpClient()

    def log(m):
        logs.append("  " * depth + str(m))

    log(f"[d={depth}] {url}")

    status, final_url, html = client.get(url)
    log(f"HTTP {status} -> {final_url}")

    if status == 0:
        return {"success": False, "error": "Fetch gagal", "logs": logs, "raw": html[:500]}

    log(f"HTML: {len(html)} bytes")

    parsed = urlparse(final_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    # === PRIORITAS 1: window.location.href ===
    loc_match = re.search(r'window\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']', html)
    if loc_match:
        target = loc_match.group(1).replace("\\/", "/")
        if target.startswith("http") and "sfl.gl" not in target and "khaddavi" not in target:
            log(f"FINAL (window.location): {target}")
            return {"success": True, "url": target, "method": "window-location", "logs": logs}

    # === PRIORITAS 2: Kalau halaman khaddavi, panggil /api/go ===
    if "khaddavi" in final_url.lower():
        log("Halaman khaddavi terdeteksi, coba /api/go...")
        api_url = try_api_go(final_url, client, logs)
        if api_url:
            return {"success": True, "url": api_url, "method": "api-go", "logs": logs}

    # === PRIORITAS 3: redirect final ===
    if final_url != url and "sfl.gl" not in final_url and "khaddavi" not in final_url:
        log(f"FINAL via redirect: {final_url}")
        return {"success": True, "url": final_url, "method": "redirect-final", "logs": logs}

    # === PRIORITAS 4: Rekursif — shortener lain ===
    all_urls = extract_urls(html.replace("\\/", "/"))
    shorteners = [
        u for u in all_urls
        if ("sfl.gl" in u or "khaddavi" in u or "redirect.php" in u)
        and u not in visited
        and u != url
        and not has_fragment(u)
    ]
    for s in shorteners[:2]:
        log(f"Rekursif: {s}")
        sub = bypass(s, depth + 1, max_depth, visited)
        if sub.get("success"):
            sub["logs"] = logs + sub.get("logs", [])
            return sub

    return {"success": False, "error": "Gagal detect", "logs": logs}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        target = params.get("url", [None])[0]
        if not target:
            self._json(400, {"success": False, "error": "Param 'url' wajib"})
            return
        try:
            self._json(200, bypass(target))
        except Exception as e:
            import traceback
            self._json(500, {
                "success": False,
                "error": str(e),
                "trace": traceback.format_exc(),
            })

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, ensure_ascii=False).encode())
