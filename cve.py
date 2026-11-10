#!/usr/bin/env python3
"""Recent CVEs from NVD, marked with CISA KEV (known exploited). Stdlib only; reads public feeds, nothing else.

  cyber cve [keyword ...]            CVEs published in the last 3 days, newest first
  cyber cve CVE-2024-3400            one CVE in detail (scores, CWE, KEV, references)
  cyber cve --kev [keyword ...]      CISA KEV additions (actively exploited)
  options: --days N  --severity critical|high|medium|low (that level and above)  --limit N  --json  --refresh

Responses are cached (NVD 1 h, KEV 6 h); a stale cache is used when a feed is unreachable.
An optional NVD API key (NVD_API_KEY) raises NVD's rate limit; none is required.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import ssl
import sys
import time
import urllib.parse
import urllib.request

NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0"
KEV = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
CVE_ID = re.compile(r"^CVE-\d{4}-\d{4,}$", re.I)


def tls_context():
    """Default trust store plus the OS bundle; python.org builds on macOS often ship without CA certificates."""
    ctx = ssl.create_default_context()
    for bundle in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"):
        if os.path.exists(bundle):
            ctx.load_verify_locations(bundle)
            break
    return ctx


class Feed:
    def __init__(self, cache, refresh=False, api_key=""):
        self.cache, self.refresh, self.api_key = cache, refresh, api_key

    def get(self, url, ttl):
        path = os.path.join(self.cache, hashlib.sha1(url.encode()).hexdigest() + ".json") if self.cache else ""
        if path and not self.refresh and os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        headers = {"User-Agent": "cyberroot-cve/1"}
        if self.api_key and url.startswith(NVD):
            headers["apiKey"] = self.api_key
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30, context=tls_context()) as r:
                data = json.load(r)
        except Exception as e:  # network, HTTP or JSON error: fall back to any cached copy
            if path and os.path.exists(path):
                print(f"feed unreachable ({e}); using cached data", file=sys.stderr)
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            raise SystemExit(f"cannot reach {url.split('?')[0]}: {e}")
        if path:
            os.makedirs(self.cache, exist_ok=True)
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(path + ".tmp", path)
        return data


def kev_index(feed):
    progress("CISA KEV")
    return {v["cveID"]: v for v in feed.get(KEV, 6 * 3600).get("vulnerabilities", [])}


def score(cve):
    """(score, severity) preferring CVSS 3.1, then 4.0, 3.0, 2; NVD's own (Primary) score before the CNA's."""
    metrics = cve.get("metrics", {})
    for key in ("cvssMetricV31", "cvssMetricV40", "cvssMetricV30", "cvssMetricV2"):
        for entry in sorted(metrics.get(key) or [], key=lambda e: e.get("type") != "Primary"):
            data = entry.get("cvssData", {})
            if data.get("baseScore") is not None:
                return float(data["baseScore"]), (data.get("baseSeverity") or entry.get("baseSeverity") or "").upper()
    return None, ""


def row(cve, kev):
    s, sev = score(cve)
    desc = next((d["value"] for d in cve.get("descriptions", []) if d.get("lang") == "en"), "")
    cwes = sorted({d["value"] for w in cve.get("weaknesses", []) for d in w.get("description", [])
                   if d.get("value", "").startswith("CWE-")})
    k = kev.get(cve["id"])
    return {"id": cve["id"], "published": cve.get("published", "")[:10], "score": s, "severity": sev,
            "status": cve.get("vulnStatus", ""), "kev": bool(k), "kev_added": k and k.get("dateAdded"),
            "ransomware": k and k.get("knownRansomwareCampaignUse") == "Known", "cwe": cwes,
            "description": " ".join(desc.split()), "url": f"https://nvd.nist.gov/vuln/detail/{cve['id']}",
            "references": [r["url"] for r in cve.get("references", [])][:8]}


def nvd_recent(feed, days, keywords):
    end = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)  # hour-stable cache key
    start = end - dt.timedelta(days=min(days, 120))  # NVD allows at most 120 days per query
    params = {"pubStartDate": start.strftime("%Y-%m-%dT%H:%M:%S.000"), "pubEndDate": end.strftime("%Y-%m-%dT%H:%M:%S.000"),
              "resultsPerPage": 2000, "noRejected": ""}
    if keywords:
        params["keywordSearch"] = " ".join(keywords)
    found, total, index, pages = [], None, 0, 0
    while total is None or index < min(total, 8000):
        if pages >= 4 and not feed.api_key:
            time.sleep(6)  # public rate limit: 5 requests per rolling 30 s
        progress(f"NVD page {pages + 1}" + (f"/{-(-min(total, 8000) // 2000)}" if total else ""))
        query = urllib.parse.urlencode({**params, "startIndex": index}).replace("noRejected=", "noRejected")
        page = feed.get(f"{NVD}?{query}", 3600)
        total = page.get("totalResults", 0)
        found += [v["cve"] for v in page.get("vulnerabilities", [])]
        index += page.get("resultsPerPage", 2000) or 2000
        pages += 1
    progress("")
    return found


def progress(text):
    """One self-erasing status line on stderr so slow feeds do not look frozen."""
    if sys.stderr.isatty():
        sys.stderr.write("\r\x1b[K" + (f"\x1b[2mfetching {text}…\x1b[0m" if text else ""))
        sys.stderr.flush()


def kev_recent(feed, days, keywords):
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    words = [w.lower() for w in keywords]
    out = []
    for v in kev_index(feed).values():
        text = " ".join(str(v.get(k, "")) for k in ("cveID", "vendorProject", "product", "vulnerabilityName", "shortDescription")).lower()
        if v.get("dateAdded", "") >= since and all(w in text for w in words):
            out.append({"id": v["cveID"], "published": v.get("dateAdded", ""), "score": None, "severity": "",
                        "kev": True, "kev_added": v.get("dateAdded"), "ransomware": v.get("knownRansomwareCampaignUse") == "Known",
                        "vendor": v.get("vendorProject", ""), "product": v.get("product", ""), "due": v.get("dueDate", ""),
                        "description": v.get("vulnerabilityName") or f"{v.get('vendorProject', '')} {v.get('product', '')}".strip(),
                        "url": f"https://nvd.nist.gov/vuln/detail/{v['cveID']}"})
    return sorted(out, key=lambda r: (r["published"], r["id"]), reverse=True)


class Style:
    def __init__(self, on):
        # Theme colours come from ailab (CYBER_C_*); standalone runs use plain terminal colours.
        env = (lambda k, d: os.environ.get(k, d) if on else "")
        self.id, self.text, self.dim = env("CYBER_C_ID", "\x1b[36m"), env("CYBER_C_TEXT", ""), env("CYBER_C_DIM", "\x1b[2m")
        self.bold, self.red, self.yellow, self.reset = ("\x1b[1m", "\x1b[31m", "\x1b[33m", "\x1b[0m") if on else ("",) * 4

    def sev(self, sev):
        return {"CRITICAL": self.bold + self.red, "HIGH": self.red, "MEDIUM": self.yellow}.get(sev, self.text)


def clip(text, n):
    return text if len(text) <= n else text[:max(0, n - 1)] + "…"


def print_table(rows, total, st, hint):
    cols = shutil.get_terminal_size((120, 20)).columns
    for r in rows:
        s = f"{r['score']:4.1f}" if r["score"] is not None else "   -"
        kev = f"{st.bold}{st.red}KEV{st.reset}" if r["kev"] else "   "
        head = f"{st.id}{r['id']:<16}{st.reset} {st.sev(r['severity'])}{s} {r['severity'][:4] or '    ':<4}{st.reset} " \
               f"{st.dim}{r['published']}{st.reset} {kev}  "
        print(head + st.text + clip(r["description"], cols - 45) + st.reset)
    print(f"{st.dim}{len(rows)} of {total} · {hint}{st.reset}", file=sys.stderr)


def print_detail(r, st):
    s = f"{r['score']} {r['severity']}" if r["score"] is not None else "not scored yet"
    print(f"{st.bold}{st.id}{r['id']}{st.reset}  {st.sev(r['severity'])}{s}{st.reset}  {st.dim}published {r['published']} · {r['status']}{st.reset}")
    if r["kev"]:
        print(f"{st.bold}{st.red}KEV{st.reset} {st.text}known exploited, added {r['kev_added']}"
              f"{' · used in ransomware' if r['ransomware'] else ''}{st.reset}")
    if r["cwe"]:
        print(f"{st.dim}weakness{st.reset} {st.text}{', '.join(r['cwe'])}{st.reset}")
    print()
    print(st.text + r["description"] + st.reset)
    print()
    for u in [r["url"]] + r["references"]:
        print(f"  {st.dim}{u}{st.reset}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="cyber cve", description="Recent CVEs from NVD, marked with CISA KEV.")
    p.add_argument("keywords", nargs="*", help="keywords (all must match) or one CVE ID")
    p.add_argument("--days", type=int, default=3)
    p.add_argument("--severity", type=str.upper, choices=list(RANK))
    p.add_argument("--kev", action="store_true", help="CISA known exploited additions instead of all new CVEs")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--json", action="store_true")
    p.add_argument("--refresh", action="store_true", help="ignore the cache")
    p.add_argument("--cache", default=os.environ.get("CYBER_CVE_CACHE", ""), help=argparse.SUPPRESS)
    a = p.parse_args(argv)
    feed = Feed(a.cache, a.refresh, os.environ.get("NVD_API_KEY", ""))
    st = Style(sys.stdout.isatty() and not os.environ.get("NO_COLOR") and not a.json)

    if len(a.keywords) == 1 and CVE_ID.match(a.keywords[0]):
        cve_id = a.keywords[0].upper()
        found = feed.get(f"{NVD}?{urllib.parse.urlencode({'cveId': cve_id})}", 3600).get("vulnerabilities", [])
        if not found:
            raise SystemExit(f"{cve_id} not found in NVD")
        r = row(found[0]["cve"], kev_index(feed))
        print(json.dumps(r, indent=2)) if a.json else print_detail(r, st)
        return 0

    if a.kev:
        rows = kev_recent(feed, a.days, a.keywords)
    else:
        kev = kev_index(feed)
        rows = [row(c, kev) for c in nvd_recent(feed, a.days, a.keywords)]
        rows.sort(key=lambda r: (r["published"], r["id"]), reverse=True)
    if a.severity:
        rows = [r for r in rows if RANK.get(r["severity"], 0) >= RANK[a.severity]]
    total = len(rows)
    rows = rows[:max(0, a.limit)]
    if a.json:
        print(json.dumps(rows, indent=2))
    elif not rows:
        print(f"no matching CVEs in the last {a.days} days", file=sys.stderr)
    else:
        print_table(rows, total, st, "cyber cve CVE-ID for details · --severity high · --kev · --days N · --json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
