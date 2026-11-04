#!/usr/bin/env python
"""username-enum — handle -> which sites have an account with that username.

Sherlock-style existence check: hit each site's profile URL for the handle and
decide exists / absent / unknown from the status code or a page marker. Threaded
so a ~25-site sweep finishes in a couple of seconds.

The site list is a plain dict (SITES) so it's trivial to extend. Detection is
deliberately simple and PER SITE:
    method "status"  -> exists if HTTP 200, absent if 404, else unknown.
    method "notfound"-> 200 for everyone; marker is the "no such user" text (present => absent).
    method "string"  -> the site answers 200 for everything, so existence keys on
                        a marker substring: present => exists, absent => absent.
These are HEURISTIC. Social sites block bots and soft-404 (200 + "not found"
page), so treat a hit as a LEAD (a profile URL to eyeball), not proof — same
discipline as scrapers/tinder_check. Confirm a handle match with a second tie
(same face/email/etc.) before calling two accounts the same person.

USAGE
    poetry run python username-enum/username_enum.py korrart
    poetry run python username-enum/username_enum.py korrart --only github,gitlab,telegram
    poetry run python username-enum/username_enum.py korrart --timeout 8 --threads 16
    poetry run python username-enum/username_enum.py --selftest          # offline, no network
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# name: (url_template, method, marker)
# marker only used by method "string". url_template takes the handle via .format().
# ponytail: curated high-signal set, not Sherlock's full 400. Add a row to extend;
# the adversarial live test is what proves each row's method/marker, not this guess.
SITES = {
    "GitHub":    ("https://github.com/{}",                 "status", None),
    "Keybase":   ("https://keybase.io/{}",                 "status", None),
    "Replit":    ("https://replit.com/@{}",                "status", None),
    "Pastebin":  ("https://pastebin.com/u/{}",             "status", None),
    "DockerHub": ("https://hub.docker.com/v2/users/{}/",   "status", None),
    "Dev.to":    ("https://dev.to/{}",                     "status", None),
    "About.me":  ("https://about.me/{}",                   "status", None),
    "Gumroad":   ("https://{}.gumroad.com",                "status", None),
    "Wordpress": ("https://{}.wordpress.com",              "status", None),
    "Chess.com": ("https://api.chess.com/pub/player/{}",   "status", None),
    "Telegram":  ("https://t.me/{}",                       "string", "tgme_page_title"),
    "TikTok":    ("https://www.tiktok.com/@{}",            "string", '"uniqueId"'),
    "Steam":     ("https://steamcommunity.com/id/{}",      "notfound", "The specified profile could not be found"),
}


def classify(method, marker, status, text):
    """(verdict, detail). verdict in {exists, absent, unknown}."""
    if method == "status":
        if status == 200:
            return "exists", "HTTP 200"
        if status == 404:
            return "absent", "HTTP 404"
        if status == 410:
            return "absent", "HTTP 410 (gone)"
        return "unknown", "HTTP %s" % status
    if method == "notfound":
        # site 200s for everyone; marker = the "no such user" text. present => absent.
        if status != 200:
            return "unknown", "HTTP %s" % status
        return ("absent", "not-found text") if marker in (text or "") else ("exists", "no not-found text")
    # string method: site 200s for everyone, existence keys on the marker
    if status != 200:
        return "unknown", "HTTP %s" % status
    if marker and marker in (text or ""):
        return "exists", "marker found"
    return "absent", "marker absent"


def check(handle, name, session, timeout):
    url_tmpl, method, marker = SITES[name]
    url = url_tmpl.format(handle)
    try:
        r = session.get(url, headers={"User-Agent": UA}, timeout=timeout,
                        allow_redirects=True)
    except Exception as e:
        return {"site": name, "url": url, "verdict": "unknown", "detail": str(e)[:60]}
    # only the string method needs the body; keep status-method cheap
    text = r.text if method in ("string", "notfound") else ""
    status = r.status_code
    if "wordpress.com/typo" in r.url:   # unregistered subdomain redirects to a signup page (200)
        status = 404
    verdict, detail = classify(method, marker, status, text)
    return {"site": name, "url": url, "verdict": verdict, "detail": detail}


def sweep(handle, sites, timeout, threads):
    import requests  # lazy: keep the network dep off the --selftest path
    session = requests.Session()
    with ThreadPoolExecutor(max_workers=threads) as pool:
        rows = list(pool.map(lambda n: check(handle, n, session, timeout), sites))
    rows.sort(key=lambda r: ({"exists": 0, "unknown": 1, "absent": 2}[r["verdict"]], r["site"]))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check which sites have an account for a username.")
    ap.add_argument("handle", nargs="?", help="the username/handle to check")
    ap.add_argument("--only", help="comma-separated subset of site names (case-insensitive)")
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--selftest", action="store_true", help="offline classifier check")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.handle:
        ap.error("give a handle, or --selftest")

    sites = list(SITES)
    if args.only:
        want = {s.strip().lower() for s in args.only.split(",")}
        sites = [n for n in SITES if n.lower() in want]
        if not sites:
            ap.error("--only matched no known sites: %s" % ", ".join(SITES))

    rows = sweep(args.handle.lstrip("@"), sites, args.timeout, args.threads)
    w = max(len(r["site"]) for r in rows)
    print("%-*s  %-8s  %s" % (w, "SITE", "VERDICT", "URL / DETAIL"))
    for r in rows:
        tail = r["url"] if r["verdict"] == "exists" else "%s (%s)" % (r["url"], r["detail"])
        print("%-*s  %-8s  %s" % (w, r["site"], r["verdict"], tail))
    hits = [r for r in rows if r["verdict"] == "exists"]
    print("\n%d exist, %d absent, %d unknown. 'exists' = a LEAD to eyeball, not a confirmed link."
          % (len(hits), sum(r["verdict"] == "absent" for r in rows),
             sum(r["verdict"] == "unknown" for r in rows)))
    return 0


def selftest():
    # status method
    assert classify("status", None, 200, "")[0] == "exists"
    assert classify("status", None, 404, "")[0] == "absent"
    assert classify("status", None, 403, "")[0] == "unknown"
    # string method: marker present/absent on a 200, non-200 is unknown
    assert classify("string", "uid", 200, "...uid...")[0] == "exists"
    assert classify("string", "uid", 200, "nope")[0] == "absent"
    assert classify("string", "uid", 429, "...uid...")[0] == "unknown", "rate-limit != exists"
    assert classify("status", None, 410, "")[0] == "absent"
    assert classify("notfound", "gone", 200, "user gone")[0] == "absent"
    assert classify("notfound", "gone", 200, "profile")[0] == "exists"
    assert classify("notfound", "gone", 429, "profile")[0] == "unknown"
    print("username-enum selftest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
