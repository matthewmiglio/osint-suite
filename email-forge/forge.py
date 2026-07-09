#!/usr/bin/env python
"""email-forge — name + domain -> candidate email addresses.

Pure stdlib. Emits the common corporate/personal address patterns for a name so
you can feed them to gravatar, dehashed, or an SMTP verifier. These are
*candidates*, not proof: guessed schemes, verify before trusting.
"""
import argparse
import sys

# ponytail: fixed pattern set covers ~all real-world schemes; a configurable
# template engine would be a bug farm nobody needs. Add a row if one's missing.
PATTERNS = [
    "{f}",        # john
    "{l}",        # doe
    "{f}.{l}",    # john.doe
    "{f}{l}",     # johndoe
    "{fi}{l}",    # jdoe
    "{fi}.{l}",   # j.doe
    "{f}{li}",    # johnd
    "{f}.{li}",   # john.d
    "{f}_{l}",    # john_doe
    "{f}-{l}",    # john-doe
    "{l}.{f}",    # doe.john
    "{l}{f}",     # doejohn
    "{l}{fi}",    # doej
    "{fi}{li}",   # jd
]


def candidates(name, domain):
    parts = [p for p in name.replace(",", " ").split() if p]
    if not parts:
        return []
    if len(parts) == 1:
        return [f"{parts[0].lower()}@{domain}"]
    f, l = parts[0].lower(), parts[-1].lower()
    ctx = {"f": f, "l": l, "fi": f[:1], "li": l[:1]}
    out = []
    for p in PATTERNS:
        addr = f"{p.format(**ctx)}@{domain}"
        if addr not in out:
            out.append(addr)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate candidate emails from a name + domain.")
    ap.add_argument("--name", help='Full name, e.g. "John Doe"')
    ap.add_argument("--domain", help="Domain, e.g. example.com")
    ap.add_argument("--selftest", action="store_true", help="Run offline self-check and exit.")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.name or not args.domain:
        ap.error("--name and --domain are required (or use --selftest)")
    for addr in candidates(args.name, args.domain):
        print(addr)
    return 0


def selftest():
    got = candidates("John Doe", "example.com")
    for expect in ("john.doe@example.com", "jdoe@example.com", "jd@example.com"):
        assert expect in got, (expect, got)
    assert candidates("Cher", "x.com") == ["cher@x.com"], "single token"
    assert candidates("  ", "x.com") == [], "empty name"
    assert len(got) == len(set(got)), "dupes"
    print("email-forge selftest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
