#!/usr/bin/env python
"""ip-intel — IP address -> geolocation + ASN via ip-api.com (free, no key).

The network fetch and the formatting are split so the parsing stays testable
offline (see --selftest). Free tier: HTTP only, ~45 req/min, no key. Omit --ip to
look up your own egress IP.
"""
import argparse
import sys

FIELDS = ("status,message,query,country,regionName,city,zip,lat,lon,timezone,"
          "isp,org,as,reverse,mobile,proxy,hosting")


def fetch(ip=""):
    import requests  # lazy: keep the network dep off the self-test path
    url = f"http://ip-api.com/json/{ip}?fields={FIELDS}"
    r = requests.get(url, timeout=10, headers={"User-Agent": "osint-suite"})
    r.raise_for_status()
    return r.json()


def summarize(data):
    if data.get("status") != "success":
        return f"lookup failed: {data.get('message', 'unknown error')}"
    return "\n".join([
        f"ip:       {data.get('query')}",
        f"location: {data.get('city')}, {data.get('regionName')}, "
        f"{data.get('country')} {data.get('zip')}".strip(),
        f"coords:   {data.get('lat')}, {data.get('lon')}  ({data.get('timezone')})",
        f"asn:      {data.get('as')}",
        f"isp/org:  {data.get('isp')} / {data.get('org')}",
        f"reverse:  {data.get('reverse')}",
        f"flags:    mobile={data.get('mobile')} proxy={data.get('proxy')} hosting={data.get('hosting')}",
    ])


def main(argv=None):
    ap = argparse.ArgumentParser(description="IP geolocation + ASN (ip-api.com, free).")
    ap.add_argument("--ip", default="", help="IP to look up (default: your own egress IP).")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    print(summarize(fetch(args.ip)))
    return 0


def selftest():
    # offline: run a canned ip-api response through the formatter
    sample = {
        "status": "success", "query": "8.8.8.8", "country": "United States",
        "regionName": "Virginia", "city": "Ashburn", "zip": "20149",
        "lat": 39.03, "lon": -77.5, "timezone": "America/New_York",
        "isp": "Google LLC", "org": "Google Public DNS", "as": "AS15169 Google LLC",
        "reverse": "dns.google", "mobile": False, "proxy": False, "hosting": True,
    }
    out = summarize(sample)
    assert "AS15169 Google LLC" in out, out
    assert "Ashburn" in out and "8.8.8.8" in out, out
    assert summarize({"status": "fail", "message": "reserved range"}).startswith("lookup failed"), "error path"
    print("ip-intel selftest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
