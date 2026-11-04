#!/usr/bin/env python
"""email-accounts — email -> which sites have an account registered to it.

Thin wrapper around `holehe` (the maintained 120+-site account-existence checker:
it probes each site's password-reset / signup endpoint to tell whether the email
is registered, WITHOUT alerting the target). We wrap rather than reinvent on
purpose — 120 brittle per-site probes is a maintenance bug farm somebody else
already maintains.

Needs holehe (`poetry add holehe`, or `pip install holehe` in the env). This is
the email counterpart to username-enum: a "used" site is a LEAD (an account to
confirm), not proof of identity — several people can share forwarding addresses,
and holehe false-positives. Corroborate before folding a link in.

The stdout parser is split from the subprocess call so it's testable offline
(see --selftest). holehe itself does the network.

USAGE
    poetry run python email-accounts/accounts.py foo@bar.com
    poetry run python email-accounts/accounts.py foo@bar.com --timeout 60
    poetry run python email-accounts/accounts.py --selftest          # offline
"""
import argparse
import shutil
import subprocess
import sys


def parse_holehe(text):
    """holehe stdout -> sorted list of domains where the email is USED ([+] lines).

    A real used line is '[+] <domain>' optionally followed by recovery metadata
    holehe discovered: a partial recovery email, phone, and/or full name, e.g.
    '[+] twitter.com ab****@gmail.com / +1******89 / FullName Jane Doe'. So the
    domain is the FIRST whitespace-delimited token after '[+]', not the whole
    remainder. The legend line ('[+] Email used, [-] ...') is excluded because
    its first token ('Email') is not a domain (no dot).
    """
    sites = set()
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("[+]"):
            continue
        rest = line[3:].strip()
        if not rest:
            continue
        token = rest.split()[0]
        if "." in token and "@" not in token:
            sites.add(token)
    return sorted(sites)


def run_holehe(email, timeout):
    # --no-color: keep ANSI codes out of stdout so '[+]' parsing holds regardless
    #   of termcolor version / FORCE_COLOR (termcolor only auto-strips on a pipe).
    # --no-clear: print a newline instead of a clear-screen escape before results.
    base = [email, "--only-used", "--no-color", "--no-clear"]
    exe = shutil.which("holehe")
    cmd = [exe] + base if exe else [sys.executable, "-m", "holehe.core"] + base
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc.stdout + proc.stderr


def main(argv=None):
    ap = argparse.ArgumentParser(description="Find sites where an email is registered (via holehe).")
    ap.add_argument("email", nargs="?", help="the email address to check")
    ap.add_argument("--timeout", type=float, default=120.0, help="seconds for the holehe run")
    ap.add_argument("--selftest", action="store_true", help="offline parser check")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.email:
        ap.error("give an email, or --selftest")

    if not shutil.which("holehe"):
        try:
            import holehe  # noqa: F401  module present even if console script isn't on PATH
        except ImportError:
            print("holehe not installed. Run:  poetry add holehe   (or: pip install holehe)",
                  file=sys.stderr)
            return 2
    try:
        out = run_holehe(args.email, args.timeout)
    except subprocess.TimeoutExpired:
        print("holehe timed out — raise --timeout or check the network", file=sys.stderr)
        return 1
    sites = parse_holehe(out)
    if sites:
        print("registered (LEADS — verify before pivoting):")
        for s in sites:
            print("  " + s)
        print(f"\n{len(sites)} site(s). Each is an account to confirm, not a proven identity link.")
    else:
        print("no sites reported the email as registered (or holehe was rate-limited).")
    return 0


def selftest():
    sample = (
        "\033[H\033[J\n"                      # clear-screen escape (default, no --no-clear)
        "*********************\n     foo@bar.com\n*********************\n"
        "[+] github.com\n"                     # bare used line
        "[+] pinterest.com\n"
        "[+] twitter.com ab****@gmail.com / +1******89\n"   # used + recovery email/phone
        "[+] protonmail.com / FullName Jane Doe\n"           # used + full name
        "[-] instagram.com\n"                  # not used (suppressed by --only-used anyway)
        "[x] rate.com\n"                       # rate-limited (ditto) — must be excluded
        "[+] Email used, [-] Email not used, [x] Rate limit\n"  # legend
        "121 websites checked in 2.9 seconds\n"
    )
    got = parse_holehe(sample)
    # recovery-suffixed hits (twitter, protonmail) MUST survive; legend/[-]/[x] excluded
    assert got == ["github.com", "pinterest.com", "protonmail.com", "twitter.com"], got
    assert parse_holehe("") == [], "empty"
    assert parse_holehe("[+] Email used, [-] Email not used, [x] Rate limit") == [], "legend excluded"
    assert parse_holehe("[+] nope has spaces") == [], "non-domain first token excluded"
    print("email-accounts selftest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
