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

SHORTENER_DOMAINS = [
    "sfl.gl", "safelink", "safelinku", "khaddavi", "comun.id",
    "bit.ly", "tinyurl", "shorturl", "s.id", "tiny.cc",
    "rebrand.ly", "cutt.ly", "shorte.st", "adf.ly",
]

ASSET_BLACKLIST = [
    "google", "gstatic", "cloudflare", "cdn.",
    "jquery", "bootstrap", "fontawesome", "analytics",
    "doubleclick", "facebook", "twitter", "whatsapp",
    "schema.org", "w.org", "wp.com", "gravatar",
    "generatepress", "wordpress.org", "themeforest",
    "elementor", "w3.org", "googleapis",
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
    return not is_shortener(url) and not is_asset(url)


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


def bypass(url, depth=0, max_depth=6, visited=None):
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

    # === PRIORITAS 1: window.location.href ===
    loc_match = re.search(
        r'window\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']',
        html
    )
    if loc_match:
        target = loc_match.group(1).replace("\\/", "/")
        if target.startswith("http"):
            log(f"FINAL (window.location.href): {target}")
            return {"success": True, "url": target, "method": "window-location", "logs": logs}

    # === PRIORITAS 2: redirect final ===
    if final_url != url and not is_shortener(final_url) and not is_asset(final_url):
        log(f"FINAL via redirect: {final_url}")
        return {"success": True, "url": final_url, "method": "redirect-final", "logs": logs}

    # === PRIORITAS 3: JS var ===
    for pattern in [
        r'location\.replace\(["\'](https?:[^"\']+)["\']\)',
        r'location\.assign\(["\'](https?:[^"\']+)["\']\)',
        r'["\'](?:url|link|target|redirect|real_url|final_url|destination)["\']\s*[:=]\s*["\'](https?:[^"\']+)["\']',
    ]:
        m = re.search(pattern, html, re.I)
        if m:
            js_target = m.group(1).replace("\\/", "/")
            if js_target.startswith("http") and not is_shortener(js_target) and not is_asset(js_target):
                log(f"FINAL (JS var): {js_target}")
                return {"success": True, "url": js_target, "method": "js-var", "logs": logs}

    # === PRIORITAS 4: URL final di HTML ===
    all_urls = extract_urls(html.replace("\\/", "/"))
    final_candidates = [u for u in all_urls if is_candidate(u)]
    if final_candidates:
        log(f"Kandidat final: {final_candidates[0]}")
        return {"success": True, "url": final_candidates[0], "method": "html-url", "candidates": final_candidates[:5], "logs": logs}

    # === PRIORITAS 5: rekursif shortener ===
    shorteners_in_html = [u for u in all_urls if is_shortener(u) and u not in visited and u != url]
    for s in shorteners_in_html[:3]:
        log(f"Shortener lain: {s}, rekursif...")
        sub = bypass(s, depth + 1, max_depth, visited)
        if sub.get("success"):
            sub["logs"] = logs + sub.get("logs", [])
            return sub

    # === PRIORITAS 6: endpoint POST/GET ===
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

                loc_m = re.search(r'window\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']', txt)
                if loc_m:
                    target = loc_m.group(1).replace("\\/", "/")
                    if target.startswith("http"):
                        return {"success": True, "url": target, "method": f"{method}-window-location", "logs": logs}

                if fu != final_url and not is_shortener(fu) and not is_asset(fu):
                    return {"success": True, "url": fu, "method": f"{method}-redirect", "logs": logs}

                if is_shortener(fu) and fu not in visited:
                    sub = bypass(fu, depth + 1, max_depth, visited)
                    if sub.get("success"):
                        sub["logs"] = logs + sub.get("logs", [])
                        return sub

                found = [u for u in extract_urls(txt.replace("\\/", "/")) if is_candidate(u)]
                if found:
                    return {"success": True, "url": found[0], "method": f"{method}-body", "candidates": found[:5], "logs": logs}
            except Exception as e:
                log(f"{method} err: {e}")

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
