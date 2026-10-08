from http.server import BaseHTTPRequestHandler
import json
import re
import base64
import binascii
from urllib.parse import urlparse, parse_qs
import cloudscraper

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

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "android", "mobile": True}
)


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


def filter_real(urls):
    blacklist = [
        "sfl.gl", "safelink", "khaddavi", "google", "gstatic", "cloudflare",
        "cdn.", "jquery", "bootstrap", "fontawesome", "analytics",
        "doubleclick", "facebook", "twitter", "whatsapp", "schema.org",
        "w.org", "wp.com", "gravatar",
    ]
    return [u for u in urls if not any(b in u.lower() for b in blacklist)]


def find_all_hidden(html):
    results = []

    for blob in re.findall(r'[A-Za-z0-9+/=]{30,}', html):
        dec = b64_decode(blob)
        if dec and "http" in dec:
            results.extend(filter_real(extract_urls(dec)))

    for blob in re.findall(r'[0-9a-fA-F]{30,}', html):
        dec = hex_decode(blob)
        if dec and "http" in dec:
            results.extend(filter_real(extract_urls(dec)))

    for m in re.findall(r'(?:var|let|const)\s+\w+\s*=\s*["\'](https?://[^"\']+)["\']', html):
        results.append(m)

    for m in re.findall(
        r'["\'](?:url|link|target|redirect|destination|href)["\']\s*:\s*["\'](https?://[^"\']+)["\']',
        html, re.I
    ):
        results.append(m)

    for m in re.findall(
        r'data-(?:url|href|link|target|redirect|dest)=["\'](https?://[^"\']+)["\']',
        html, re.I
    ):
        results.append(m)

    for m in re.findall(
        r'<meta[^>]+content=["\']\d+;\s*url=(https?://[^"\']+)["\']',
        html, re.I
    ):
        results.append(m)

    for m in re.findall(r'<a[^>]+href=["\'](https?://[^"\']+)["\']', html, re.I):
        if not any(x in m for x in ["khaddavi", "sfl.gl", "safelink"]):
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
        if any(k in m.lower() for k in ["api", "go", "step", "link", "redirect", "get"]):
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


def bypass(url):
    logs = []

    def log(m):
        logs.append(str(m))

    log(f"Target: {url}")

    r = scraper.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
    log(f"HTTP {r.status_code} -> {r.url}")

    for h in r.history:
        log(f"redirect: {h.status_code} {h.headers.get('Location','')}")

    html = r.text
    log(f"HTML size: {len(html)}")

    log("Cari hidden payload...")
    hidden = find_all_hidden(html)
    if hidden:
        log(f"Ketemu {len(hidden)} kandidat")
        return {
            "success": True,
            "url": hidden[0],
            "method": "hidden-in-html",
            "candidates": hidden[:10],
            "logs": logs,
        }

    endpoints = find_step_endpoints(html)
    tokens = find_tokens(html)
    log(f"Endpoints: {endpoints}")
    log(f"Tokens: {list(tokens.keys())}")

    base = f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}"

    for ep in endpoints[:5]:
        full = ep if ep.startswith("http") else base + ep
        for method in ("POST", "GET"):
            try:
                if method == "POST":
                    res = scraper.post(full, headers=HEADERS, data=tokens, timeout=20)
                else:
                    res = scraper.get(full, headers=HEADERS, params=tokens, timeout=20)
                log(f"{method} {full} -> {res.status_code}")

                found = find_all_hidden(res.text)
                if found:
                    return {
                        "success": True,
                        "url": found[0],
                        "method": f"{method}-{ep}",
                        "logs": logs,
                    }

                try:
                    j = res.json()
                    for k in ("url", "link", "target", "redirect"):
                        if k in j and isinstance(j[k], str) and j[k].startswith("http"):
                            return {
                                "success": True,
                                "url": j[k],
                                "method": f"{method}-json",
                                "logs": logs,
                            }
                except Exception:
                    pass
            except Exception as e:
                log(f"{method} err: {e}")

    all_urls = filter_real(extract_urls(html))
    if all_urls:
        return {
            "success": True,
            "url": all_urls[0],
            "method": "fallback",
            "candidates": all_urls[:10],
            "logs": logs,
        }

    return {
        "success": False,
        "error": "Gagal detect",
        "logs": logs,
        "endpoints": endpoints,
    }


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


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(bypass(sys.argv[1]), indent=2, ensure_ascii=False))
