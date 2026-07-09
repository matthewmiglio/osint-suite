# dehashed

DeHashed **Search API v2** client. Searches the breach-data table and saves
every matching record to disk. Single file: `dehashed.py`.

## Setup
1. You need a paid DeHashed **Search subscription** with **credits** (pay per
   query). A free monitoring-only account will not work.
2. Put your key in `dehashed/.env` (copy `.env.example`):
   ```
   DEHASHED_API_KEY=your_key_here
   ```
   `.env` is git-ignored. `DEHASHED_EMAIL` is not needed (v2 uses header auth).
3. From the repo root: `poetry install` (adds `requests` + `python-dotenv`).

## Usage
```bash
poetry run python dehashed/dehashed.py --type email  --value foo@bar.com
poetry run python dehashed/dehashed.py --type domain --value example.com --size 100 --max-pages 5
poetry run python dehashed/dehashed.py --selftest        # offline mock, no API call, no credits
```

`--type` fields: `email`, `username`, `ip_address`, `phone`, `name`, `address`,
`domain`, `vin`, `password`, `hashed_password`.

Flags: `--size N` (records/page), `--max-pages N` (credit guard: max API calls
per run), `--wildcard`, `--regex`, `--no-dedupe`, `--no-csv`, `--outdir PATH`.

## Cost & safety
DeHashed is pay-per-query and **each page is one credit-consuming call**. The
remaining `balance` is printed after every page, `--max-pages` caps spend per
run, and hard failures (401 bad key / 429 rate-limited / non-200) are **not
retried** so a broken call never burns credits in a loop.

## Output (git-ignored)
`dehashed/results/dehashed_<field>_<value>_<timestamp>.json` (aggregated raw
records) plus a flattened `.csv`. Both `results/` and `.env` are excluded by the
repo `.gitignore`.

## Programmatic use
```python
from dehashed import DeHashedClient, load_api_key, save_results
client = DeHashedClient(load_api_key())
result = client.search_all("domain", "example.com", max_pages=3)
save_results(result)
```
