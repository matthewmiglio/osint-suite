#!/usr/bin/env python
"""domain-intel — domain -> registration (RDAP) + subdomains (crt.sh) + A records.

Three free, keyless sources:
  RDAP (rdap.org)  -> registrar, created/expiry dates, nameservers, status.
  crt.sh           -> subdomains seen in issued TLS certs (cert transparency).
  socket (stdlib)  -> A records for the apex.
RDAP is the modern replacement for port-43 whois: HTTPS + JSON, no parsing of
free-text whois blobs. Subdomains are the pivot — each is new infrastructure that
can feed spiderfoot / ip-intel.

All parsing is split from the fetch so it stays testable offline (see --selftest).
requests for the HTTP calls; A records use stdlib socket.

USAGE
    poetry run python domain-intel/domain.py example.com
    poetry run python domain-intel/domain.py example.com --no-subs
    poetry run python domain-intel/domain.py --selftest          # offline
"""
import argparse
import socket
import sys


def parse_rdap(j):
    """RDAP domain JSON -> {registrar, created, expires, status, nameservers}."""
    out = {"domain": j.get("ldhName"), "status": ", ".join(j.get("status", []))}
    for ev in j.get("events", []):
        action = ev.get("eventAction")
        if action == "registration":
            out["created"] = ev.get("eventDate")
        elif action in ("expiration",):
            out["expires"] = ev.get("eventDate")
    for ent in j.get("entities", []):
        if "registrar" in ent.get("roles", []):
            # registrar name lives in the vCard: ["vcard", [ ["fn", {}, "text", NAME], ... ]]
            for item in ent.get("vcardArray", [None, []])[1]:
                if item and item[0] == "fn":
                    out["registrar"] = item[3]
    out["nameservers"] = [ns.get("ldhName") for ns in j.get("nameservers", []) if ns.get("ldhName")]
    return out


def parse_crtsh(records, domain):
    """crt.sh JSON rows -> sorted unique subdomains of `domain` (wildcards stripped)."""
    subs = set()
    suffix = "." + domain.lower()
    for row in records:
        for name in (row.get("name_value", "") or "").splitlines():
            name = name.strip().lstrip("*.").lower()
            if name and (name == domain.lower() or name.endswith(suffix)):
                subs.add(name)
    return sorted(subs)


def fetch_rdap(domain):
    import requests
    r = requests.get(f"https://rdap.org/domain/{domain}",
                     headers={"User-Agent": "osint-suite"}, timeout=15)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def fetch_crtsh(domain):
    import requests
    r = requests.get("https://crt.sh/", params={"q": "%." + domain, "output": "json"},
                     headers={"User-Agent": "osint-suite"}, timeout=30)
    r.raise_for_status()
    return r.json()


def a_records(domain):
    try:
        return sorted(set(socket.gethostbyname_ex(domain)[2]))
    except OSError:
        return []


def main(argv=None):
    ap = argparse.ArgumentParser(description="Domain registration + subdomains + A records.")
    ap.add_argument("domain", nargs="?", help="the domain, e.g. example.com")
    ap.add_argument("--no-subs", action="store_true", help="skip the crt.sh subdomain pull")
    ap.add_argument("--selftest", action="store_true", help="offline parser check")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.domain:
        ap.error("give a domain, or --selftest")
    domain = args.domain.strip().lower()
    for pfx in ("https://", "http://"):
        if domain.startswith(pfx):
            domain = domain[len(pfx):]
    domain = domain.split("/")[0]  # drop any path

    rdap = fetch_rdap(domain)
    if rdap is None:
        print(f"no RDAP record for {domain} (unregistered, or TLD has no RDAP server)")
    else:
        d = parse_rdap(rdap)
        print(f"domain:     {d.get('domain')}")
        print(f"registrar:  {d.get('registrar')}")
        print(f"created:    {d.get('created')}")
        print(f"expires:    {d.get('expires')}")
        print(f"status:     {d.get('status')}")
        for ns in d.get("nameservers", []):
            print(f"nameserver: {ns}")

    ips = a_records(domain)
    for ip in ips:
        print(f"A record:   {ip}  (feed to ip-intel)")

    if not args.no_subs:
        try:
            subs = parse_crtsh(fetch_crtsh(domain), domain)
        except Exception as e:
            # crt.sh is frequently slow or returns 503 / an HTML error page
            # instead of JSON. A transient failure there must not kill the run —
            # the RDAP and A-record results above are still worth printing.
            print(f"\nsubdomains: crt.sh lookup failed ({type(e).__name__}); "
                  f"skipping. Retry later or re-run with --no-subs.")
        else:
            print(f"\nsubdomains ({len(subs)} from cert transparency):")
            for s in subs:
                print("  " + s)
    return 0


def selftest():
    rdap = {
        "ldhName": "EXAMPLE.COM", "status": ["client transfer prohibited"],
        "events": [{"eventAction": "registration", "eventDate": "1995-08-14T04:00:00Z"},
                   {"eventAction": "expiration", "eventDate": "2025-08-13T04:00:00Z"}],
        "entities": [{"roles": ["registrar"],
                      "vcardArray": ["vcard", [["version", {}, "text", "4.0"],
                                               ["fn", {}, "text", "RESERVED-Internet"]]]}],
        "nameservers": [{"ldhName": "A.IANA-SERVERS.NET"}, {"ldhName": "B.IANA-SERVERS.NET"}],
    }
    d = parse_rdap(rdap)
    assert d["registrar"] == "RESERVED-Internet", d
    assert d["created"].startswith("1995") and d["expires"].startswith("2025"), d
    assert d["nameservers"] == ["A.IANA-SERVERS.NET", "B.IANA-SERVERS.NET"], d

    rows = [{"name_value": "www.example.com\n*.example.com"},
            {"name_value": "mail.example.com"},
            {"name_value": "evil.com"}]           # unrelated domain must be dropped
    subs = parse_crtsh(rows, "example.com")
    assert subs == ["example.com", "mail.example.com", "www.example.com"], subs
    print("domain-intel selftest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
