# osint-suite

A personal OSINT / recon monorepo. Five independent tools that used to be
separate repos, folded together for one place to find and run them.

> Authorized use only: your own accounts, consenting targets, CTFs, or
> engagements you have permission to run. Scraping and password cracking against
> third parties without consent may be illegal where you are.

## Layout

```
osint-suite/
├── CLAUDE.md            # you are here: lay of the land + usage
├── pyproject.toml       # shared Poetry env (Python tools only)
├── .gitignore
├── pw-cracker/          # Python  – offline hash cracker (rockyou-style)
│   ├── crack.py
│   └── README.md
├── scrapers/            # Chrome extensions (JavaScript, Manifest V3)
│   ├── instagram/       #   – scrape a profile's followers + following
│   └── facebook/        #   – scrape a profile's photo album + comments
├── dehashed/            # Python  – DeHashed v2 breach-search API client
│   ├── dehashed.py
│   └── README.md
└── spiderfoot/          # Python  – full OSINT automation suite (vendored 3rd-party)
```

## What's Python and what isn't (read this before the Poetry section)

Three of the five are Python, and they do NOT all share dependencies:

| Module               | Stack                    | Runs via                          |
| -------------------- | ------------------------ | --------------------------------- |
| `pw-cracker`         | Python (stdlib + bcrypt) | the shared Poetry env below       |
| `dehashed`           | Python (requests+dotenv) | the shared Poetry env below       |
| `scrapers/instagram` | JS Chrome extension      | loaded unpacked in Chrome         |
| `scrapers/facebook`  | JS Chrome extension      | loaded unpacked in Chrome         |
| `spiderfoot`         | Python, own pinned deps  | its own isolated venv (see below) |

So the "shared environment" is real but small: it owns `pw-cracker` and
`dehashed`. The extensions have no Python. SpiderFoot ships ~25 old pinned dependencies
(`cryptography<4`, `pyOpenSSL<22`, `PyPDF2<2`, `networkx<2.7`, ...) plus its own
`requirements.txt` and `.git`; merging those into the shared env would drag
everything backwards, so it stays isolated on purpose.

## Shared Poetry environment

One virtualenv for the Python tools we own. `package-mode = false`, so Poetry
just manages the env; nothing is built or installed as a package.

```bash
cd C:\My_Files\my_programs\osint-suite
poetry install                 # creates the venv, installs deps (bcrypt, requests, python-dotenv)
poetry run python pw-cracker/crack.py <hash>
```

Add a Python dependency for a tool we own: `poetry add <pkg>`.

## Usage per module

### pw-cracker  (Python)
Offline hash cracker: md5/sha1/sha256/sha512 (unsalted + simple-salted),
bcrypt, and Django pbkdf2_sha256. Full detail in `pw-cracker/README.md`.

```bash
poetry run python pw-cracker/crack.py <hash>
poetry run python pw-cracker/crack.py --batch pw-cracker/hashes.txt
```

### scrapers/instagram  (Chrome extension)
Scrapes a target profile's followers and following (handle, name, profile pic)
into `Downloads/ig-scrape-<handle>/`. See `scrapers/instagram/guide.md`.

1. `chrome://extensions` → enable **Developer mode** → **Load unpacked** →
   select `scrapers/instagram`.
2. Log into Instagram, open the target profile.
3. Click the extension icon, enter the handle, click scrape.

### scrapers/facebook  (Chrome extension)
Walks a profile's photo lightbox, scraping image + caption + location + poster +
date + visible comments into per-photo folders under Downloads. See
`scrapers/facebook/README.md`.

1. `chrome://extensions` → **Developer mode** → **Load unpacked** →
   select `scrapers/facebook`.
2. Log into Facebook, open the target's **Photos** tab, click a photo to open
   the lightbox.
3. Click the extension icon, set folder / max photos / delay, **Start scraping**.

### dehashed  (Python)
DeHashed v2 API client: search breach data by email / domain / username / etc.
and save JSON + CSV to `dehashed/results/`. API key lives in `dehashed/.env`
(git-ignored). Full detail in `dehashed/README.md`.

```bash
poetry run python dehashed/dehashed.py --type email --value foo@bar.com
poetry run python dehashed/dehashed.py --selftest      # offline mock, no credits
```

### spiderfoot  (Python, isolated)
Vendored SpiderFoot 4.0: 200+ modules, CLI-only (web UI stripped out). Do NOT install it into the
shared env; give it its own isolated venv (its old pinned deps stay contained):

```bash
cd spiderfoot
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python sf.py -M                                 # list available modules
python sf.py -s example.com -u footprint -o csv # scan by use-case, CSV to stdout
```

## Notes

- **Git**: single git repo on `main`, SpiderFoot fully vendored (its internal
  `.git` was removed). No remote configured yet; add one at the top level when
  ready.
- **pw-cracker data** (`rockyou.txt`, `hashes*.txt`, cracked output) is
  git-ignored: large and/or sensitive. See `.gitignore`.
- **Secrets**: `dehashed/.env` (your DeHashed API key) and `dehashed/results/`
  (pulled breach data) are git-ignored. Never commit them.
