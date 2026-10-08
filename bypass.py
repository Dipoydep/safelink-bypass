#!/usr/bin/env python3
"""
Safelink Bypass - Termux Edition
Jalan di Termux, pake IP HP -> lolos Cloudflare.
"""
import sys
import json
import re
import random
import base64
import requests

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


def fetch(url, session=None, allow_redirects=True):
    s = session or requests.Session()
    try:
        r = s.get(url, headers=HEADERS, timeout=20, allow_redirects=allow_redirects)
        return r.status_code, r.url, r.text
    except Exception as e:
        return 0, url, f"ERROR: {e}"


def post(url, session=None, json_data=None, data=None, extra_headers=None):
    s = session or requests.Session()
    h = dict(HEADERS)
    if extra_headers:
        h.update(extra_headers)
    try:
        r = s.post(url, headers=h, timeout=20, json=json_data, data=data)
        return r.status_code, r.url, r.text
    except Exception as e:
        return 0, url, f"ERROR: {e}"


def build_token(session, html, verbose=True):
    """Bikin _token = XSRF-TOKEN + '#' + base64(fingerprint)."""
    def log(msg):
        if verbose:
            print(msg)

    # Ambil XSRF-TOKEN dari cookie
    xsrf = None
    for c in session.cookies:
        if c.name == "XSRF-TOKEN":
            xsrf = c.value
            break

    if xsrf:
        log(f"[4] XSRF-TOKEN (raw): {xsrf[:60]}...")
        log(f"    Panjang: {len(xsrf)}")
    else:
        log(f"[4] XSRF-TOKEN gak ada di cookie")
        xsrf = ""

    # Fingerprint SANGAT sederhana — 1 karakter aja
    fingerprint = "a"
    fp_b64 = base64.b64encode(fingerprint.encode()).decode()
    u = "#" + fp_b64

    # _token = xsrf (dipotong sampe 128 - len(u)) + u
    max_xsrf = max(0, 128 - len(u))
    token = xsrf[:max_xsrf] + u

    log(f"[5] _token (panjang {len(token)}): {token[:60]}...")
    return token


def bypass_safelink(url, verbose=True):
    def log(msg):
        if verbose:
            print(msg)

    session = requests.Session()
    log(f"[*] Target: {url}")

    # STEP 1: Fetch URL awal
    status, final_url, html = fetch(url, session)
    log(f"[1] HTTP {status} -> {final_url}")

    if "Attention Required" in html or "cf-browser-verification" in html:
        return {"success": False, "error": "Cloudflare block", "url": url}

    # STEP 2: Cari redirect.php
    rp_match = re.search(r'["\'](https?://[^"\']*?/redirect\.php[^"\']*)["\']', html)
    rp_url = rp_match.group(1) if rp_match else "https://app.khaddavi.net/redirect.php"
    log(f"[2] redirect.php: {rp_url}")

    # STEP 3: POST redirect.php
    st, kh_url, kh_html = post(rp_url, session, json_data={"_a": 0})
    log(f"[3] POST redirect.php -> {st} -> {kh_url}")

    if "khaddavi" not in kh_url:
        kh_match = re.search(r'["\'](https?://app\.khaddavi\.net/[^"\']+)["\']', html)
        if kh_match:
            kh_url = kh_match.group(1)
            log(f"[3] khaddavi URL: {kh_url}")

    if not kh_url or "khaddavi" not in kh_url:
        return {"success": False, "error": "Gak dapet khaddavi URL"}

    # Parse base domain
    parsed = re.match(r'(https?://[^/]+)', kh_url)
    base = parsed.group(1) if parsed else "https://app.khaddavi.net"
    log(f"[+] Base: {base}")

    # STEP 3.5: Fetch halaman khaddavi (biar cookie XSRF ke-set)
    st, _, kh_html = fetch(kh_url, session)
    log(f"[3.5] Fetch khaddavi -> {st}")
    log(f"    Cookies: {[c.name for c in session.cookies]}")

    # STEP 4-5: Bikin _token
    token = build_token(session, kh_html, verbose)

    # STEP 6: /api/session
    extra_headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Origin": base,
        "Referer": kh_url,
    }
    st, _, body = post(
        f"{base}/api/session",
        session,
        json_data={"_token": token},
        extra_headers=extra_headers,
    )
    log(f"[6] /api/session -> {st}")
    log(f"    {body[:200]}")

    # STEP 7: /api/go
    st, _, body = post(
        f"{base}/api/go",
        session,
        json_data={"key": 1, "size": "1000.2000", "ado": None},
        extra_headers=extra_headers,
    )
    log(f"[7] /api/go -> {st}")
    log(f"    {body[:300]}")

    # Parse JSON
    try:
        data = json.loads(body)
        target = data.get("url") or data.get("target") or data.get("link")
        if target:
            log(f"\n[OK] FINAL: {target}")
            return {"success": True, "url": target, "method": "api-go"}
    except Exception:
        pass

    # Fallback: cari URL di body
    urls = re.findall(r'https?://[^\s"\'<>\\]+', body)
    for u in urls:
        if not any(x in u.lower() for x in ["khaddavi", "sfl.gl", "google", "gstatic", "cloudflare", "wp.com", "w.org", "schema"]):
            log(f"\n[OK] FINAL (fallback): {u}")
            return {"success": True, "url": u, "method": "fallback"}

    return {
        "success": False,
        "error": "Gak dapet URL target",
        "session_body": body[:300],
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python bypass.py <safelink_url>")
        print("Contoh: python bypass.py https://sfl.gl/7vUwMV")
        sys.exit(1)

    target = sys.argv[1]
    result = bypass_safelink(target)
    print("\n=== HASIL ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
