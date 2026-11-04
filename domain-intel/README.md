# domain-intel

Domain → registration details + subdomains + A records, from three free keyless
sources.

```bash
poetry run python domain-intel/domain.py example.com
poetry run python domain-intel/domain.py example.com --no-subs
poetry run python domain-intel/domain.py --selftest     # offline parser check
```

- **Consumes:** a domain (apex, e.g. `example.com`).
- **Emits:**
  - **RDAP** (rdap.org) → registrar, created/expiry dates, status, nameservers.
  - **crt.sh** (cert transparency) → subdomains — each new infrastructure to feed
    `spiderfoot` / `ip-intel`.
  - **A records** (stdlib `socket`) → apex IPs, straight into `ip-intel`.
- **Cost:** free.

## Notes
- RDAP is the modern replacement for port-43 whois: HTTPS + JSON, no free-text
  parsing. Some TLDs/ccTLDs have no RDAP server → "no RDAP record" is possible for
  a registered domain.
- crt.sh can be slow or briefly 503 (and sometimes returns an HTML error page
  instead of JSON). When that happens the subdomain lookup is skipped with a
  notice and the RDAP + A-record results still print; retry later or use
  `--no-subs`. The subdomain list reflects certs that were logged, so it misses
  hosts that never got a public cert. Wildcard entries (`*.example.com`) are
  collapsed to the apex.
