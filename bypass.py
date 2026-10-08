#!/usr/bin/env python3
import sys
import json
import re
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


def post(url, session=None, json_data=None):
    s = session or requests.Session()
    try:
        r = s.post(url, headers=HEADERS, timeout=20, json=json_data)
        return r.status_code, r.url, r.text
    except Exception as e:
        return 0, url, f"ERROR: {e}"


def bypass_safelink(url, verbose=True):
    def log(msg):
        if verbose:
            print(msg)

    session = requests.Session()
    log(f"[*] Target: {url}")

    # STEP 1: Fetch URL awal
    status, final_url, html = fetch(url, session)
    log(f"[1] HTTP {status} -> {final_url}")

    # STEP 2: Cari redirect.php
    rp_match = re.search(r'["\'](https?://[^"\']*?/redirect\.php[^"\']*)["\']', html)
    rp_url = rp_match.group(1) if rp_match else None

    if rp_url:
        log(f"[2] redirect.php: {rp_url}")
        status, kh_url, kh_html = post(rp_url, session, json_data={"_a": 0})
        log(f"[3] POST redirect.php -> {status} -> {kh_url}")
    else:
        log("[2] redirect.php gak ketemu, coba fetch ulang")
        kh_url = final_url
        kh_html = html

    # STEP 3: Parse base domain khaddavi
    if "khaddavi" not in kh_url:
        kh_match = re.search(r'["\'](https?://app\.khaddavi\.net/[^"\']+)["\']', html)
        if kh_match:
            kh_url = kh_match.group(1)
            log(f"[3] khaddavi URL: {kh_url}")

    if "khaddavi" not in kh_url:
        return {"success": False, "error": "Gak dapet khaddavi URL"}

    parsed = re.match(r'(https?://[^/]+)', kh_url)
    base = parsed.group(1) if parsed else "https://app.khaddavi.net"
    log(f"[+] Base: {base}")

    # STEP 4: /api/session
    st, _, body = post(f"{base}/api/session", session, json_data={"_token": "test"})
    log(f"[4] /api/session -> {st}")
    log(f"    {body[:200]}")

    # STEP 5: /api/go
    st, _, body = post(f"{base}/api/go", session, json_data={"key": 1, "size": "1000.2000", "ado": None})
    log(f"[5] /api/go -> {st}")
    log(f"    {body[:300]}")

    # Parse JSON
    try:
        data = json.loads(body)
        target = data.get("url") or data.get("target") or data.get("link")
        if target:
            log(f"\n[✓] FINAL: {target}")
            return {"success": True, "url": target, "method": "api-go"}
    except Exception:
        pass

    # Fallback: cari URL di body
    urls = re.findall(r'https?://[^\s"\'<>\\]+', body)
    for u in urls:
        if not any(x in u.lower() for x in ["khaddavi", "sfl.gl", "google", "gstatic", "cloudflare", "wp.com", "w.org", "schema"]):
            log(f"\n[✓] FINAL (fallback): {u}")
            return {"success": True, "url": u, "method": "fallback"}

    return {"success": False, "error": "Gak dapet URL target", "go_body": body[:500]}


def main():
    if len(sys.argv) < 2:
        print("Usage: python bypass.py <safelink_url>")
        sys.exit(1)
    result = bypass_safelink(sys.argv[1])
    print("\n=== HASIL ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
