from http.server import BaseHTTPRequestHandler
import json
import re
import base64
import binascii
from urllib.parse import urlparse, parse_qs, urlencode
import urllib.request
import urllib.error
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

# Cuma blacklist — bukan whitelist
SHORTENER_DOMAINS = [
    "sfl.gl", "safelink", "khaddavi", "comun.id",
    "bit.ly", "tinyurl", "shorturl", "s.id", "tiny.cc",
    "rebrand.ly", "cutt.ly", "shorte.st", "adf.ly",
]

# Asset / tracker yang harus di-skip
ASSET_BLACKLIST = [
    "google", "gstatic", "cloudflare", "cdn.",
    "jquery", "bootstrap", "fontawesome", "analytics",
    "doubleclick", "facebook", "twitter", "whatsapp",
    "schema.org", "w.org", "wp.com", "gravatar",
]


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, url, e.read().decode("utf-8", "ignore")
    except Exception as e:
        return 0, url, f"ERROR: {e}"


def http_post(url, data, timeout=20):
    body = urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers=HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, url, e.read().decode("utf-8", "ignore")
    except Exception as e:
        return 0, url, f"ERROR: {e}"


def b64_decode(s):
    try:
        return base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "ignore")
    except Exception:
        return None


def hex_decode(s):
    try:
        return binascii.unhexlify(s).decode("utf-8", "ignore")
    except Exception:
        return None


def extract_urls(text):
    return re.findall(r'https?://[^\s"\'<>\\]+', text)


def is_shortener(url):
    return any(d in url.lower() for d in SHORTENER_DOMAINS)


def is_asset(url):
    return any(d in url.lower() for d in ASSET_BLACKLIST)


def is_candidate(url):
    """URL kandidat final: bukan shortener, bukan asset."""
    return not is_shortener(url) and not is_asset(url)


def filter_real(urls):
    return [u for u in urls if is_candidate(u)]


def find_all_hidden(html):
    results = []

    for blob in re.findall(r'[A-Za-z0-9+/=]{30,}', html):
        dec = b64_decode(blob)
        if dec and "http" in dec:
            results.extend(extract_urls(dec))

    for blob in re.findall(r'[0-9a-fA-F]{30,}', html):
        dec = hex_decode(blob)
        if dec and "http" in dec:
            results.extend(extract_urls(dec))

    for m in re.findall(r'(?:var|let|const)\s+\w+\s*=\s*["\'](https?://[^"\']+)["\']', html):
        results.append(m)

    for m in re.findall(
        r'["\'](?:url|link|target|redirect|destination|href|real_url|final_url)["\']\s*:\s*["\'](https?://[^"\']+)["\']',
        html, re.I
    ):
        results.append(m)

    for m in re.findall(
        r'data-(?:url|href|link|target|redirect|dest|real)=["\'](https?://[^"\']+)["\']',
        html, re.I
    ):
        results.append(m)

    for m in re.findall(
        r'<meta[^>]+content=["\']\d+;\s*url=(https?://[^"\']+)["\']',
        html, re.I
    ):
        results.append(m)

    for m in re.findall(r'<a[^>]+href=["\'](https?://[^"\']+)["\']', html, re.I):
        results.append(m)

    seen = set()
    final = []
    for u in results:
        if u not in seen:
            seen.add(u)
            final.append(u)
    return final


def find_step_endpoints(html):
    endpoints = []
    for m in re.findall(r'(?:fetch|\.ajax|\.get|\.post|axios\.\w+)\s*\(\s*["\']([^"\']+)["\']', html):
        endpoints.append(m)
    for m in re.findall(r'<form[^>]+action=["\']([^"\']+)["\']', html, re.I):
        endpoints.append(m)
    for m in re.findall(r'["\'](/[a-z0-9_\-]+/[a-z0-9_\-/]+)["\']', html, re.I):
        if any(k in m.lower() for k in ["api", "go", "step", "link", "redirect", "get", "ready"]):
            endpoints.append(m)
    for m in re.findall(r'["\'](https?://[^"\']*?/(?:go|ready|redirect|link|get)[^"\']*)["\']', html, re.I):
        endpoints.append(m)
    return list(set(endpoints))


def find_tokens(html):
    tokens = {}
    for m in re.findall(
        r'<input[^>]+name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']',
        html, re.I
    ):
        tokens[m[0]] = m[1]
    for m in re.findall(
        r'["\'](?:token|csrf|_token|key|nonce)["\']\s*:\s*["\']([^"\']+)["\']',
        html, re.I
    ):
        tokens["_js_token"] = m
    return tokens


def find_ready_url(html):
    m = re.search(r'(https?://sfl\.gl/ready/go\?t=[A-Za-z0-9]+)', html)
    if m:
        return m.group(1)
    m = re.search(r'["\'](/ready/go\?t=[A-Za-z0-9]+)["\']', html)
    if m:
        return "https://sfl.gl" + m.group(1)
    return None


def bypass(url, depth=0, max_depth=8, visited=None):
    if visited is None:
        visited = set()

    if url in visited:
        return {"success": False, "error": "Loop detected", "url": url, "logs": []}

    visited.add(url)

    if depth >= max_depth:
        return {"success": False, "error": "Max depth reached", "url": url, "logs": []}

    logs = []

    def log(m):
        logs.append("  " * depth + str(m))

    log(f"[d={depth}] {url}")

    status, final_url, html = http_get(url)
    log(f"HTTP {status} -> {final_url}")

    if status == 0:
        return {"success": False, "error": "Fetch gagal", "logs": logs, "raw": html[:500]}

    log(f"HTML: {len(html)} bytes")

    # Kalau redirect udah keluar dari shortener = final
    if final_url != url and not is_shortener(final_url) and not is_asset(final_url):
        log(f"FINAL via redirect: {final_url}")
        return {"success": True, "url": final_url, "method": "redirect-final", "logs": logs}

    # KHUSUS ready/go
    if "ready/go" in final_url or "/ready/" in final_url:
        log("Halaman ready — cari payload...")

        hidden = [u for u in find_all_hidden(html) if is_candidate(u)]
        for u in hidden:
            log(f"Kandidat final: {u}")
            return {"success": True, "url": u, "method": "ready-final", "candidates": hidden[:10], "logs": logs}

        endpoints = find_step_endpoints(html)
        tokens = find_tokens(html)
        log(f"Ready endpoints: {endpoints}")

        base = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"
        for ep in endpoints[:10]:
            full = ep if ep.startswith("http") else base + ep
            for method in ("POST", "GET"):
                try:
                    if method == "POST":
                        st, fu, txt = http_post(full, tokens)
                    else:
                        st, fu, txt = http_get(full + ("?" + urlencode(tokens) if tokens else ""))
                    log(f"  {method} {full} -> {st} -> {fu}")

                    if fu != final_url and not is_shortener(fu) and not is_asset(fu):
                        return {"success": True, "url": fu, "method": f"ready-{method}-redirect", "logs": logs}

                    found = [u for u in find_all_hidden(txt) if is_candidate(u)]
                    if found:
                        return {"success": True, "url": found[0], "method": f"ready-{method}-body", "candidates": found[:10], "logs": logs}
                except Exception as e:
                    log(f"  err: {e}")

        if hidden:
            return {"success": True, "url": hidden[0], "method": "ready-fallback", "candidates": hidden[:10], "logs": logs}

    # Ready URL di HTML
    ready_url = find_ready_url(html)
    if ready_url:
        log(f"Ketemu ready URL: {ready_url}")
        sub = bypass(ready_url, depth + 1, max_depth, visited)
        if sub.get("success"):
            sub["logs"] = logs + sub.get("logs", [])
            return sub

    # Hidden payload
    log("Cari hidden payload...")
    hidden = find_all_hidden(html)
    candidates = [u for u in hidden if is_candidate(u)]

    if candidates:
        log(f"Kandidat final: {len(candidates)}")
        return {"success": True, "url": candidates[0], "method": "hidden-final", "candidates": candidates[:10], "logs": logs}

    # Rekursif kalau ketemu shortener lain
    shorteners_in_html = [u for u in hidden if is_shortener(u) and u not in visited]
    for s in shorteners_in_html[:3]:
        log(f"Shortener lain: {s}, rekursif...")
        sub = bypass(s, depth + 1, max_depth, visited)
        if sub.get("success"):
            sub["logs"] = logs + sub.get("logs", [])
            return sub

    # Endpoints
    endpoints = find_step_endpoints(html)
    tokens = find_tokens(html)
    log(f"Endpoints: {endpoints}")

    base = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"

    for ep in endpoints[:8]:
        full = ep if ep.startswith("http") else base + ep
        for method in ("POST", "GET"):
            try:
                if method == "POST":
                    st, fu, txt = http_post(full, tokens)
                else:
                    st, fu, txt = http_get(full + ("?" + urlencode(tokens) if tokens else ""))
                log(f"{method} {full} -> {st} -> {fu}")

                if fu != final_url and not is_shortener(fu) and not is_asset(fu):
                    return {"success": True, "url": fu, "method": f"{method}-redirect", "logs": logs}

                if is_shortener(fu) and fu not in visited:
                    log(f"Rekursif ke: {fu}")
                    sub = bypass(fu, depth + 1, max_depth, visited)
                    if sub.get("success"):
                        sub["logs"] = logs + sub.get("logs", [])
                        return sub

                found = [u for u in find_all_hidden(txt) if is_candidate(u)]
                if found:
                    return {"success": True, "url": found[0], "method": f"{method}-body", "candidates": found[:10], "logs": logs}

                short_in_body = [u for u in find_all_hidden(txt) if is_shortener(u) and u not in visited]
                if short_in_body:
                    log(f"Shortener di body: {short_in_body[0]}, rekursif...")
                    sub = bypass(short_in_body[0], depth + 1, max_depth, visited)
                    if sub.get("success"):
                        sub["logs"] = logs + sub.get("logs", [])
                        return sub

                rdy = find_ready_url(txt)
                if rdy and rdy not in visited:
                    log(f"Ready URL di body: {rdy}")
                    sub = bypass(rdy, depth + 1, max_depth, visited)
                    if sub.get("success"):
                        sub["logs"] = logs + sub.get("logs", [])
                        return sub
            except Exception as e:
                log(f"{method} err: {e}")

    all_urls = filter_real(extract_urls(html))
    if all_urls:
        return {"success": True, "url": all_urls[0], "method": "fallback", "candidates": all_urls[:10], "logs": logs}

    return {"success": False, "error": "Gagal detect", "logs": logs, "endpoints": endpoints}


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
