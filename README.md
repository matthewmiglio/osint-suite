# osint-suite

A personal OSINT and recon monorepo that collects several standalone tools into
one place. It spans offline password cracking, browser-based social-media
scraping, breach-data lookups, and a full third-party OSINT automation engine.
The Python tools we own share a single Poetry environment, while the browser
extensions and the vendored SpiderFoot run on their own. The goal is one repo to
clone, one place to look, and clear per-tool instructions so nothing needs
re-discovering later.

> Not every tool is Python and they do not all share dependencies. Read the
> per-module table below before running anything.

## Modules

| Module               | Language / stack           | What it does                                                        |
| -------------------- | -------------------------- | ------------------------------------------------------------------- |
| `pw-cracker`         | Python (stdlib + `bcrypt`) | Offline hash cracker vs. rockyou: md5/sha1/sha256/sha512 (unsalted + simple-salted), bcrypt, and Django `pbkdf2_sha256`. |
| `dehashed`           | Python (`requests`, `python-dotenv`) | DeHashed Search API v2 client: search breach data by email/domain/username/etc. and save JSON + CSV to disk. |
| `scrapers/instagram` | Chrome extension (JS, MV3) | Scrapes a target Instagram profile's followers and following (handle, name, profile pic). |
| `scrapers/facebook`  | Chrome extension (JS, MV3) | Walks a Facebook profile's photo lightbox, scraping image, caption, location, poster, date, and comments per photo. |
| `spiderfoot`         | Python (own pinned deps)   | Vendored SpiderFoot 4.0: 200+ modules, CLI-only (web UI stripped). Kept isolated because of its old dependency pins. |

Each module has its own `README.md` (or `guide.md`) with fuller detail.

## Setup

### Shared Python environment (`pw-cracker`, `dehashed`)
Requires Python 3.11+ and [Poetry](https://python-poetry.org/).

```bash
cd osint-suite
poetry install          # one venv for the Python tools we own (bcrypt, requests, python-dotenv)
```

For `dehashed`, add your API key (never committed):

```bash
cp dehashed/.env.example dehashed/.env
# then edit dehashed/.env and set DEHASHED_API_KEY=...
```

DeHashed also requires an active paid **Search Subscription** on your account
*in addition to* API credits. Credits alone return HTTP 401.

### Chrome extensions (`scrapers/instagram`, `scrapers/facebook`)
No install step. In Chrome, open `chrome://extensions`, enable **Developer
mode**, click **Load unpacked**, and select the extension folder.

### SpiderFoot (isolated)
Do not install it into the shared env; give it its own virtualenv:

```bash
cd spiderfoot
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### pw-cracker
```bash
poetry run python pw-cracker/crack.py <hash>
poetry run python pw-cracker/crack.py --batch pw-cracker/hashes.txt
```
Flags: `--algo`, `--wordlist PATH`, `--max-slow-words N`. See `pw-cracker/README.md`.

### dehashed
```bash
poetry run python dehashed/dehashed.py --type email  --value foo@bar.com
poetry run python dehashed/dehashed.py --type domain --value example.com --max-pages 5
poetry run python dehashed/dehashed.py --selftest    # offline, no API call, no credits
```
Each page is one credit-consuming call; the remaining balance prints as it runs,
and `--max-pages` caps spend. Results land in `dehashed/results/`. See
`dehashed/README.md`.

### scrapers/instagram
Load unpacked, log into Instagram, open the target profile, click the extension
icon, enter the handle, and start. Output goes to `Downloads/ig-scrape-<handle>/`.
See `scrapers/instagram/guide.md`.

### scrapers/facebook
Load unpacked, log into Facebook, open the target's **Photos** tab, click a photo
to open the lightbox, click the extension icon, set folder / max photos / delay,
and start. Output goes to per-photo folders under Downloads. See
`scrapers/facebook/README.md`.

### spiderfoot
```bash
cd spiderfoot
python sf.py -M                                    # list available modules
python sf.py -s example.com -u footprint -o csv    # scan by use-case, CSV to stdout
python sf.py -s example.com -m sfp_dnsresolve,sfp_whois -o json
```

## Disclaimers

- **Authorized use only.** Use these tools solely against your own accounts,
  data, and infrastructure, or targets you have explicit written permission to
  test (engagements, CTFs, research). Unauthorized scraping, credential
  cracking, or breach-data lookups against third parties may be illegal where
  you live and may violate the target platforms' terms of service.
- **You are responsible** for how you use this. It is provided as-is, with no
  warranty, for lawful security research and educational purposes.
- **DeHashed and other paid APIs cost real money.** You control spend via flags
  like `--max-pages`, but verify before running large jobs.
- **Handle recovered data carefully.** Cracked passwords, scraped profiles, and
  breach records are sensitive. Local outputs (`pw-cracker` wordlists/hashes,
  `dehashed/results/`, `.env`) are git-ignored by design; keep them that way.
- **SpiderFoot is third-party software** (MIT-licensed) and vendored here for
  convenience; it is not authored or maintained by this repo.
