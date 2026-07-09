#!/usr/bin/env python
"""gravatar — email -> Gravatar avatar URL + public profile.

Hash construction is offline stdlib (md5). --fetch pulls the public profile JSON
over the network (requests). Gravatar keys on the md5 of the lowercased, trimmed
email, so a hit tells you the target reused an email that has a public avatar or
profile (name, location, linked social accounts).
"""
import argparse
import hashlib
import sys

BASE = "https://www.gravatar.com"


def gravatar_hash(email):
    return hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()


def avatar_url(email, size=200, default="404"):
    return f"{BASE}/avatar/{gravatar_hash(email)}?s={size}&d={default}"


def profile_url(email):
    return f"{BASE}/{gravatar_hash(email)}.json"


def fetch_profile(email):
    import requests  # lazy import: only --fetch touches the network dep
    r = requests.get(profile_url(email), headers={"User-Agent": "osint-suite"}, timeout=10)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    entries = r.json().get("entry", [])
    return entries[0] if entries else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gravatar avatar + profile lookup by email.")
    ap.add_argument("--email")
    ap.add_argument("--size", type=int, default=200)
    ap.add_argument("--fetch", action="store_true", help="Also fetch the public profile JSON (network).")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.email:
        ap.error("--email is required (or --selftest)")
    print("hash:   ", gravatar_hash(args.email))
    print("avatar: ", avatar_url(args.email, args.size))
    print("profile:", profile_url(args.email))
    if args.fetch:
        p = fetch_profile(args.email)
        if p is None:
            print("\n(no public Gravatar profile)")
        else:
            print("\ndisplayName:", p.get("displayName"))
            print("name:       ", p.get("name"))
            print("location:   ", p.get("currentLocation"))
            for acct in p.get("accounts", []):
                print(f"account:     {acct.get('shortname')}: {acct.get('url')}")
    return 0


def selftest():
    # normalization is the real logic: trim + lowercase before hashing
    assert gravatar_hash(" Foo@Bar.com ") == gravatar_hash("foo@bar.com"), "normalize"
    h = gravatar_hash("foo@bar.com")
    assert len(h) == 32 and all(c in "0123456789abcdef" for c in h), h
    # canonical Gravatar test vector
    assert gravatar_hash("MyEmailAddress@example.com") == "0bc83cb571cd1c50ba6f3e8a78ef1346"
    assert avatar_url("foo@bar.com").startswith("https://www.gravatar.com/avatar/")
    print("gravatar selftest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
