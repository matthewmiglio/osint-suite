#!/usr/bin/env python3
"""DeHashed Search API (v2) client for the osint-suite.

Searches the DeHashed breach-data table via the v2 REST API and stores every
matching record to disk (raw JSON, plus a flattened CSV).

Auth
----
The API key is read from ``DEHASHED_API_KEY`` (a ``.env`` file next to this
script, or any parent ``.env``, or a real environment variable). It is NEVER
hard-coded. v2 authenticates with a request header, not the v1 email+key Basic
auth, so ``DEHASHED_EMAIL`` is not required.

Usage
-----
Run inside the shared Poetry env from the repo root::

    poetry install                                   # once: installs requests + python-dotenv
    poetry run python dehashed/dehashed.py --type email --value foo@bar.com
    poetry run python dehashed/dehashed.py --type domain --value example.com --size 100 --max-pages 5
    poetry run python dehashed/dehashed.py --selftest    # offline mock, no API call, no credits

Supported search fields (``--type``): email, username, ip_address, phone, name,
address, domain, vin, password, hashed_password.

Cost
----
DeHashed is pay-per-query. Each *page* is one API call that consumes credits.
The remaining ``balance`` is logged after every page, and ``--max-pages`` caps
how many calls a single run can make. Hard failures (401/429/non-200) are NOT
retried, so a broken call never burns credits in a loop.

Output
------
``dehashed/results/dehashed_<field>_<value>_<timestamp>.json`` (aggregated raw
records) and a sibling ``.csv``. The ``results/`` dir and any ``.env`` are
git-ignored.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime

API_URL = "https://api.dehashed.com/v2/search"

# v2 auth header. HTTP header names are case-insensitive, so casing is cosmetic;
# if DeHashed ever renames it, this one constant is the only thing to change.
API_KEY_HEADER = "Dehashed-Api-Key"

# v2 search fields, per the spec / DeHashed docs.
SUPPORTED_FIELDS = (
    "email", "username", "ip_address", "phone", "name",
    "address", "domain", "vin", "password", "hashed_password",
)

DEFAULT_SIZE = 100          # records per page; DeHashed allows up to 10000
DEFAULT_MAX_PAGES = 10      # credit guard: at most this many API calls per run
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


class DeHashedError(RuntimeError):
    """Any auth / network / API failure. Carries a human-readable message."""


def build_query(field: str, value: str) -> str:
    """Turn a (field, value) pair into DeHashed ``field:value`` query syntax.

    Raises ``DeHashedError`` if ``field`` is not a supported v2 search field.
    """
    if field not in SUPPORTED_FIELDS:
        raise DeHashedError(
            f"unsupported field {field!r}; choose one of: {', '.join(SUPPORTED_FIELDS)}"
        )
    return f"{field}:{value}"


class DeHashedClient:
    """Thin wrapper over the DeHashed v2 ``/search`` endpoint.

    Parameters
    ----------
    api_key : str
        DeHashed API key (from ``.env``). Required.
    timeout : int
        Per-request timeout in seconds.
    """

    def __init__(self, api_key: str, timeout: int = 30):
        if not api_key:
            raise DeHashedError("no API key provided (set DEHASHED_API_KEY in dehashed/.env)")
        # Import here so --selftest / --help work without the dependency installed.
        try:
            import requests
        except ImportError as e:  # pragma: no cover - depends on env
            raise DeHashedError("requests not installed; run `poetry install`") from e
        self._requests = requests
        self.timeout = timeout
        self.last_balance = None
        self.session = requests.Session()
        self.session.headers.update({
            API_KEY_HEADER: api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def search(self, query: str, page: int = 1, size: int = DEFAULT_SIZE,
               wildcard: bool = False, regex: bool = False, de_dupe: bool = True) -> dict:
        """POST one page of results. Returns the parsed JSON dict.

        Raises ``DeHashedError`` with a clear message on network failure or on
        401 (bad key) / 429 (rate limited) / any non-200. Never retries: a hard
        failure must not silently burn credits.
        """
        body = {
            "query": query, "page": page, "size": size,
            "wildcard": wildcard, "regex": regex, "de_dupe": de_dupe,
        }
        try:
            resp = self.session.post(API_URL, json=body, timeout=self.timeout)
        except self._requests.RequestException as e:
            raise DeHashedError(f"network error talking to DeHashed: {e}") from e

        if resp.status_code == 401:
            raise DeHashedError("401 Unauthorized — check DEHASHED_API_KEY (and that the "
                                "account has an active Search subscription + credits)")
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After", "?")
            raise DeHashedError(f"429 Too Many Requests — rate limited (Retry-After={retry}s). "
                                "Not retrying automatically.")
        if resp.status_code != 200:
            raise DeHashedError(f"HTTP {resp.status_code} from DeHashed: {resp.text[:300]}")

        try:
            data = resp.json()
        except ValueError as e:
            raise DeHashedError(f"could not parse JSON response: {e}") from e

        self.last_balance = data.get("balance")
        return data

    def search_all(self, field: str, value: str, size: int = DEFAULT_SIZE,
                   max_pages: int = DEFAULT_MAX_PAGES, **flags) -> dict:
        """Search a field and walk pagination up to ``max_pages``, aggregating
        every entry. Logs the credit balance after each page to stderr.

        Returns a dict: query, field, value, total, fetched, pages, balance, entries.
        """
        query = build_query(field, value)
        entries: list[dict] = []
        total = None
        page = 1
        while page <= max_pages:
            data = self.search(query, page=page, size=size, **flags)
            batch = data.get("entries") or []
            total = data.get("total", total)
            entries.extend(batch)
            print(f"  page {page}: +{len(batch)} entries (running {len(entries)}"
                  f"{'/' + str(total) if total is not None else ''}), "
                  f"balance={self.last_balance}", file=sys.stderr)
            if not batch:
                break
            if total is not None and len(entries) >= total:
                break
            if len(batch) < size:            # short page => last page
                break
            page += 1
        else:
            print(f"  hit --max-pages={max_pages} cap; more results may remain.", file=sys.stderr)

        return {
            "query": query, "field": field, "value": value,
            "total": total, "fetched": len(entries), "pages": page,
            "balance": self.last_balance, "entries": entries,
        }


def _flatten(value):
    """DeHashed returns list-valued fields; join them for a flat CSV cell."""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return value


def _write_csv(path: str, entries: list[dict]) -> None:
    # Column order = first-seen union of keys across all entries.
    keys: list[str] = []
    seen: set[str] = set()
    for e in entries:
        for k in e:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for e in entries:
            w.writerow({k: _flatten(v) for k, v in e.items()})


def save_results(result: dict, outdir: str = RESULTS_DIR, write_csv: bool = True):
    """Write ``result`` to a timestamped JSON file (+ CSV of entries).

    Returns ``(json_path, csv_path_or_None)``.
    """
    os.makedirs(outdir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{result['field']}_{result['value']}")[:80]
    base = os.path.join(outdir, f"dehashed_{safe}_{ts}")

    json_path = base + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    csv_path = None
    entries = result.get("entries") or []
    if write_csv and entries:
        csv_path = base + ".csv"
        _write_csv(csv_path, entries)
    return json_path, csv_path


def load_api_key() -> str | None:
    """Load ``DEHASHED_API_KEY`` from a ``.env`` (next to this script or a parent)
    or a real environment variable. Missing python-dotenv is non-fatal."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
        load_dotenv()  # cwd / parents; does not override already-set vars
    except ImportError:
        pass
    return os.getenv("DEHASHED_API_KEY")


def demo() -> None:
    """Offline self-check: exercise query-building, parsing, CSV flatten, and
    file output against a mock response. No network, no API key, no credits."""
    import tempfile

    mock_entries = [
        {"id": "1", "email": ["a@b.com"], "username": ["alice"],
         "password": ["pw1"], "database_name": "ExampleDump"},
        {"id": "2", "email": ["c@d.com"], "password": [], "name": ["Bob"]},
    ]
    result = {
        "query": "email:a@b.com", "field": "email", "value": "a@b.com",
        "total": 2, "fetched": 2, "pages": 1, "balance": 999, "entries": mock_entries,
    }

    with tempfile.TemporaryDirectory() as d:
        jp, cp = save_results(result, outdir=d, write_csv=True)
        assert os.path.exists(jp), "JSON not written"
        assert cp and os.path.exists(cp), "CSV not written"
        loaded = json.load(open(jp, encoding="utf-8"))
        assert loaded["total"] == 2 and len(loaded["entries"]) == 2, "JSON round-trip mismatch"
        rows = list(csv.DictReader(open(cp, encoding="utf-8")))
        assert len(rows) == 2, "CSV row count wrong"
        assert rows[0]["email"] == "a@b.com", "list field not flattened"
        assert rows[0]["password"] == "pw1", "password cell wrong"

    assert build_query("email", "x@y.com") == "email:x@y.com"
    try:
        build_query("bogus", "x")
        raise AssertionError("bad field should have raised")
    except DeHashedError:
        pass

    print("selftest OK: query build, field validation, JSON + CSV output, list flattening")


def main() -> None:
    ap = argparse.ArgumentParser(description="DeHashed v2 search -> local JSON/CSV")
    ap.add_argument("--type", "--field", dest="field", choices=sorted(SUPPORTED_FIELDS),
                    help="search field (email, domain, username, ...)")
    ap.add_argument("--value", help="value to search for")
    ap.add_argument("--size", type=int, default=DEFAULT_SIZE, help=f"records per page (default {DEFAULT_SIZE})")
    ap.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES,
                    help=f"max API calls (pages) per run — credit guard (default {DEFAULT_MAX_PAGES})")
    ap.add_argument("--outdir", default=RESULTS_DIR, help="output directory (default dehashed/results/)")
    ap.add_argument("--wildcard", action="store_true", help="enable DeHashed wildcard matching")
    ap.add_argument("--regex", action="store_true", help="treat value as a regex")
    ap.add_argument("--no-dedupe", action="store_true", help="disable server-side de-duplication")
    ap.add_argument("--no-csv", action="store_true", help="write JSON only, skip the CSV")
    ap.add_argument("--selftest", action="store_true", help="offline mock check; no API call, no credits")
    args = ap.parse_args()

    if args.selftest:
        demo()
        return

    if not args.field or not args.value:
        ap.error("--type and --value are required (or run --selftest)")

    api_key = load_api_key()
    if not api_key:
        print("ERROR: DEHASHED_API_KEY not set. Put it in dehashed/.env "
              "(see dehashed/.env.example).", file=sys.stderr)
        sys.exit(2)

    client = DeHashedClient(api_key)
    try:
        result = client.search_all(
            args.field, args.value, size=args.size, max_pages=args.max_pages,
            wildcard=args.wildcard, regex=args.regex, de_dupe=not args.no_dedupe,
        )
    except DeHashedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    json_path, csv_path = save_results(result, outdir=args.outdir, write_csv=not args.no_csv)
    print(f"query   : {result['query']}")
    print(f"total   : {result['total']}   fetched: {result['fetched']}   pages: {result['pages']}")
    print(f"balance : {result['balance']} (credits remaining)")
    print(f"saved   : {json_path}")
    if csv_path:
        print(f"csv     : {csv_path}")


if __name__ == "__main__":
    main()
