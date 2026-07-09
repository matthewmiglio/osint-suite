# ip-intel  (Python, requests)

IP address → geolocation + ASN, via [ip-api.com](https://ip-api.com) (free, no
key). Omit `--ip` to look up your own egress IP.

```bash
poetry run python ip-intel/ip.py --ip 8.8.8.8
poetry run python ip-intel/ip.py                # your own IP
poetry run python ip-intel/ip.py --selftest     # offline (canned response)
```

- **Consumes:** ip_address
- **Emits:** country/region/city, coords + timezone, ASN, ISP/org, reverse DNS, mobile/proxy/hosting flags
- **Cost:** free (no key). Free tier is HTTP-only, ~45 req/min.
