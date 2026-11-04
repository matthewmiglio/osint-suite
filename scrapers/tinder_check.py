#!/usr/bin/env python
"""
tinder_check.py -- does tinder.com/@<handle> resolve to a public web profile?

FINDING (2026-07, verified with the puppeteer MCP + raw HTTP):
    tinder.com/@handle IS live for handles that have a public web profile, and
    Tinder SERVER-renders the identifying bits, so a plain requests fetch (no JS)
    is enough to tell valid from not-found:
    - VALID handle (known example: @jdmx -> "JUAN", 38): personalized
      og:title = "JUAN (@jdmx) | Tinder" and og:image = a real photo on
      images-ssl.gotinder.com; the rendered card shows name / age / photo.
    - NOT-FOUND handle: the generic SPA shell -- og:title "Tinder | Dating...",
      og:image .../static/tinder.png. This shell is byte-identical across absent
      handles (incl. random garbage), and the "may have changed their ID /
      Looking for someone" text is baked into it for EVERY handle -- so that text
      is NOT a usable signal on its own.

HOW THE VERDICT IS DECIDED
    Ignore the not-found marker (always present). Key off whether Tinder
    personalized the page for the handle:
        valid      -> og:title / og:image is personalized (name/@handle / real photo)
        not_found  -> generic shell (handle has no public web profile)
        unknown    -> non-200 / couldn't parse
    NOTE: public web profiles are OPT-IN, so not_found does NOT mean the person is
    absent from Tinder -- most users never enable one. It only means this handle
    exposes no public web profile.

USAGE
    poetry run python scrapers/tinder_check.py korrart korrahleigh mstalented
    poetry run python scrapers/tinder_check.py --batch handles.txt
    poetry run python scrapers/tinder_check.py --selftest      # offline, no network
"""
import argparse
import re
import sys

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# Signatures of the generic (deprecated / not-found) shell, from live observation.
GENERIC_TITLE_FRAG = "Tinder | Dating"        # og:title + <title> on the shell
GENERIC_IMAGE_FRAG = "static/tinder.png"      # og:image on the shell
NOT_FOUND_FRAGS = ("changed their ID", "Looking for someone")


def _meta(html, prop):
    """content of <meta property|name="prop" content="...">, order-independent."""
    for pat in (
        r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]+content=["\']([^"\']*)' % re.escape(prop),
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']%s["\']' % re.escape(prop),
    ):
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1).strip()
    return None


def classify(html):
    """Return (verdict, evidence dict). verdict in {valid, not_found}."""
    title_m = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
    ev = {
        "title": title_m.group(1).strip() if title_m else None,
        "og:title": _meta(html, "og:title"),
        "og:image": _meta(html, "og:image"),
        "not_found_marker": any(f in html for f in NOT_FOUND_FRAGS),
    }
    ogt, ogi = ev["og:title"], ev["og:image"]
    personalized = bool(
        (ogt and GENERIC_TITLE_FRAG not in ogt) or
        (ogi and GENERIC_IMAGE_FRAG not in ogi)
    )
    ev["personalized"] = personalized
    return ("valid" if personalized else "not_found"), ev


def check(handle, session):
    handle = handle.lstrip("@").strip()
    url = "https://tinder.com/@%s" % handle
    try:
        r = session.get(url, headers={"User-Agent": UA}, timeout=20)
    except Exception as e:  # network problems are not a verdict
        return {"handle": handle, "url": url, "verdict": "unknown", "error": str(e)}
    if r.status_code != 200:
        return {"handle": handle, "url": url, "verdict": "unknown",
                "error": "HTTP %s" % r.status_code}
    verdict, ev = classify(r.text)
    return {"handle": handle, "url": url, "verdict": verdict, **ev}


def selftest():
    """Prove the classifier without the network: generic shell vs a synthetic
    personalized (valid-shaped) page."""
    generic = (
        '<title>Tinder | Dating, Make Friends &amp; Meet New People</title>'
        '<meta property="og:title" content="Tinder | Dating, Make Friends">'
        '<meta property="og:image" content="https://tinder.com/static/tinder.png">'
        '<div>Looking for someone? ... may have changed their ID ...</div>'
    )
    valid = (
        '<title>Korrah, 27 | Tinder</title>'
        '<meta property="og:title" content="Korrah, 27">'
        '<meta property="og:image" content="https://images-ssl.gotinder.com/u/abc/photo.jpg">'
    )
    v1, _ = classify(generic)
    v2, _ = classify(valid)
    assert v1 == "not_found", "generic shell should be not_found, got %s" % v1
    assert v2 == "valid", "personalized page should be valid, got %s" % v2
    print("selftest OK: generic->not_found, personalized->valid")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check tinder.com/@handle web-profile validity")
    ap.add_argument("handles", nargs="*", help="one or more Tinder handles")
    ap.add_argument("--batch", help="file with one handle per line")
    ap.add_argument("--selftest", action="store_true", help="offline classifier check")
    args = ap.parse_args(argv)

    if args.selftest:
        selftest()
        return 0

    handles = list(args.handles)
    if args.batch:
        with open(args.batch, encoding="utf-8") as fh:
            handles += [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    if not handles:
        ap.error("give at least one handle, or --batch <file>, or --selftest")

    import requests  # imported here so --selftest works with no requests installed
    session = requests.Session()
    rows = [check(h, session) for h in handles]

    w = max(len(r["handle"]) for r in rows)
    print("%-*s  %-9s  %s" % (w, "HANDLE", "VERDICT", "EVIDENCE"))
    for r in rows:
        if r["verdict"] == "unknown":
            detail = r.get("error", "")
        else:
            detail = 'og:title=%r' % r.get("og:title")
        print("%-*s  %-9s  %s" % (w, r["handle"], r["verdict"], detail))

    if all(r["verdict"] == "not_found" for r in rows):
        print("\nAll not_found. Public web profiles are opt-in, so this does NOT "
              "prove absence from Tinder -- only that no handle exposes one.")
    return 0


# ponytail: requests-only on purpose -- Tinder server-renders the profile's og:title/
# og:image, so no headless browser is needed (verified: @jdmx -> valid via raw HTTP).
# If Tinder ever moves personalization to JS-only, swap check() for a Playwright
# render and read document.body.innerText; the classify() rules still apply.
if __name__ == "__main__":
    sys.exit(main())
