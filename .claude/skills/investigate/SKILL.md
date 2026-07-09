---
name: investigate
description: >
  Iteratively profile a person or entity using the osint-suite modules. Seeds
  from what the user already knows (name, email, username, phone, physical
  address, IP, domain, known/hashed passwords) and loops: discover the available
  modules, decide which ones the current facts can feed, run those, fold new
  findings back into the case file, and repeat until no module can add anything
  new. Use when the user runs /investigate, or asks to profile, enrich, pivot
  on, or "dig into" a target using this suite.
---

# /investigate — iterative OSINT pivoting across the suite

Run an enrichment fixpoint: known facts → applicable modules → run → new facts →
repeat until nothing new can be produced. You are the orchestrator; the repo's
modules are the tools.

## Safety and scope (read first)
- **Authorized targets only** (see the repo README disclaimers): the user's own
  accounts/data, or a target they have explicit permission to investigate.
- **DeHashed costs real money — but run autonomously; do NOT stop to ask.**
  Cap every credit-spending run with `--max-pages 3` (raise only for a selector
  already yielding hits) so spend stays bounded without a human gate. Log the
  planned queries and the remaining balance as you go; report spend at the end.
  Only pause for the user if the balance actually runs out or a run errors.
- Never feed recovered plaintext passwords or breach dumps into external
  services. Keep them local.

## Phase 0 — Discover the modules (redo every loop)
"Available modules" is discovered from disk, not hardcoded, so newly added tools
are picked up automatically:
1. List the repo's top-level tool directories (each is a module; each `scrapers/*`
   subdirectory is its own module).
2. Read the root `README.md` module table and each module's own
   `README.md` / `guide.md` to learn its **input selectors**, **outputs**, how to
   run it, and whether it is programmatic or a manual browser step.

Current modules (reconcile against what is actually on disk):

| Module | Consumes | Emits | How to run | Cost |
|---|---|---|---|---|
| `dehashed` | email, username, name, domain, phone, address, ip_address, password, hashed_password, vin | emails, usernames, names, passwords, hashed_passwords, addresses, phones, IPs, breach/database names | `poetry run python dehashed/dehashed.py --type <field> --value <val> --max-pages <n>` | **credits** |
| `pw-cracker` | hashed_password (optional salt) | plaintext password | `poetry run python pw-cracker/crack.py <hash>` (or `--batch file`) | free |
| `email-forge` | name, domain | candidate emails (**guesses** — verify before pivoting) | `poetry run python email-forge/forge.py --name "<name>" --domain <domain>` | free |
| `wordlist-forge` | password, name, date | candidate passwords (wordlist) → feed `pw-cracker` | `poetry run python wordlist-forge/forge.py <seeds...> --suffix <date> -o wl.txt` | free |
| `gravatar` | email | names, usernames, social profile URLs, avatar (with `--fetch`) | `poetry run python gravatar/gravatar.py --email <email> --fetch` | free |
| `phone-intel` | phone | region, carrier, line-type, timezones (context, not new selectors) | `poetry run python phone-intel/phone.py --number <e164>` | free |
| `ip-intel` | ip_address | geo (city/region/country), ASN, org, reverse-DNS domain | `poetry run python ip-intel/ip.py --ip <ip>` | free |
| `dossier` | the case file (JSON) | report + relationship graph (GraphML) + timeline (reporting sink; no new selectors) | `poetry run python dossier/dossier.py --case <case.json> --out <dir>` | free |
| `spiderfoot` | ip_address, domain, email, phone, username, name, subnet, ASN | subdomains, emails, social profiles, breach hits, infra, etc. | isolated venv: `cd spiderfoot && python sf.py -s <target>` (scan) | free |
| `scrapers/instagram` | an Instagram handle | followers + following (handles, names, pics) | **manual** browser extension (load unpacked, run, paste results back) | free |
| `scrapers/facebook` | a Facebook profile | photos, captions, locations, posters, comments | **manual** browser extension | free |

## Phase 1 — Seed the case file
Ask the user what is already known and capture it into a structured **case file**
of selectors. Prompt explicitly for: full/partial **name**, **email(s)**,
**username(s)/handle(s)**, **phone(s)**, **physical address(es)**, **IP(s)** /
**domain(s)**, **known passwords**, **hashed passwords**, and anything else
(social profile URLs, VIN, employer, etc.).

Case file entry = `{type, value, source, confidence}`. `source: "user"` for
seeds; later, `source: "<module>"` for discovered facts.

## Phase 2 — The enrichment loop (docket-driven)
This loop is driven by **data landing, not by fixed passes**. Every new datum is a
new chance for another door to open, so every new datum re-scans all modules.

Keep THREE structures:
- **case file** — facts, each `{type, value, source, confidence}`.
- **ran set** — `(module, selector-value)` pairs already executed; never re-run.
- **docket** — a live queue of pending `(module, selector-value)` runs, each with
  concrete params. This is the work list. The loop ends when, and only when, it is
  empty and nothing is still in flight.

### The re-docket step — run this EVERY time a new datum lands
"A new datum lands" = a seed is captured, a result is parsed, an async job
finishes, or the user pastes back a manual scrape. On each one:
1. **Re-enumerate modules** (redo Phase 0 — this picks up newly added tools).
2. Find every module that *consumes* the new datum's type. Also reconsider
   **combinations**: a new datum together with facts already in the case file may
   now satisfy a module that needs an input we lacked before.
3. For each resulting `(module, selector-value)`: if it is **not** in the ran set
   and **not** already on the docket, **append it to the docket** with concrete
   params. Note the obvious chains: `hashed_password` → `pw-cracker`; a cracked or
   known password → `dehashed --type password`; a username → the Instagram
   scraper; a domain/IP/phone/email → `spiderfoot`; a `name`+`domain` →
   `email-forge` → candidate emails → `gravatar` / `dehashed`; an `email` →
   `gravatar` (may surface name/username/social profiles); an `ip_address` →
   `ip-intel`; a `phone` → `phone-intel`; known passwords/names/dates →
   `wordlist-forge` → `pw-cracker`.

**Seed the docket:** run the re-docket step once for every seed fact from Phase 1.

### Work the docket — drain until empty
While the docket is non-empty, pop the next item (prefer free modules; among paid
`dehashed` runs, prefer selectors most likely to yield) and:
1. **Execute it.**
   - Programmatic (`dehashed`, `pw-cracker`, `spiderfoot`): run it. For `dehashed`,
     cap credits (`--max-pages 3`) and run — no confirmation. A slow scan
     (`spiderfoot`) may run in the background; **it is not done until its output is
     parsed** — track it as in-flight, don't treat a launched-but-unparsed scan as
     finished.
   - Manual (`scrapers/*`): tell the user exactly how to run it and what to paste
     back.
2. Move the pair into the **ran set**.
3. **Parse the output.** For **every new selector value** (dedupe against the case
   file), add it to the case file with `source: <module>` and immediately run the
   **re-docket step** on it. New data can push new items onto the docket you are
   still draining — that is the point; keep draining.

### Stop condition
**Stop only when the docket is empty AND no launched run is still pending
analysis.** A background scan you kicked off but have not yet folded in is *not* an
empty docket — wait for it, parse it, re-docket from whatever it emitted, then
re-check. Do not report back while any door is still open. A pass that produced no
new selectors is fine to note, but it only justifies stopping if it also left the
docket empty.

## Phase 3 — Document and report
Whenever the loop stops (or a pass yields nothing), report to the user:
- **New selectors**, grouped by type, each tagged with the module that found it.
- **Run log**: each `(module, input) → result count`.
- **Credits spent** (DeHashed balance delta).
- **Dead ends**: modules/selectors tried with no yield.
- **Suggested manual next steps** the automated loop can't take.

Offer to save the case file + report as a markdown file (git-ignored, e.g. under
an `investigations/` folder) if the user wants it persisted. To generate the
report, relationship graph (GraphML), and timeline automatically, write the case
file as JSON and run `dossier` on it:
`poetry run python dossier/dossier.py --case investigations/<case>.json --out investigations/<case>_dossier`.

## Notes
- The loop converges because the ran set only grows and the universe of
  `(module, selector-value)` pairs is finite: every docket item either adds new
  selectors (which may enqueue more items) or adds nothing, and no pair is ever
  worked twice. When the docket empties, no module can act on anything new.
- Prefer cheap/free modules first; save credit-spending DeHashed runs for selectors
  likely to yield, and batch where possible.

## Field notes & gotchas (living — append as you learn)
> This suite + skill combination is young. Earlier agents recorded what bit them here.
> You have standing permission to extend this list: when a run surprises you, add the
> nuance so the next agent is sharper.

**SpiderFoot**
- `sf.py -o csv` output has **no dependable header** and mixes shapes: most events are
  4 columns `[source, event-type, source-data, data]`, but some (raw URLs) land on their
  own line and a literal `Source,Type,Data` header can appear mid-file. **Parse by the
  event-type string** ("Account on External Site", "Hacked Email Address", "Username",
  "Email Address"), not by column position — position-based parsing silently mangles it.
- Highest-value free signal for a person: **`Account on External Site`** events
  (`sfp_accounts` username enumeration) — a reused handle surfaces profiles on other
  platforms (FACEIT, Pinterest, kik, IFTTT, Scribd seen in the wild). These are
  **heuristic / false-positive-prone**: mark them unverified, hand the URLs back for the
  user to confirm.
- **Slow start, buffered output.** It loads 200+ modules; the CSV can sit at 0 bytes for
  a minute+ before anything lands. An empty CSV early ≠ failure — don't kill it. Run it
  with `run_in_background` and parse on completion (passive email/username scan ≈ 1-2 min).
- An **email seed already runs username→account enumeration**, so a later username-seeded
  scan is often largely redundant. Observed in this repo: email-seed found 5 accounts,
  username-seed found only 4 (a **subset** — missed the Scribd hit) and **zero** new
  selectors. So the email seed was strictly more complete. Close the username pair for
  completeness, but don't expect it to add doors, and don't drop the email-scan results in
  favour of it.
- Seed type is auto-detected; a bare human name → weak `HUMAN_NAME` seed most passive
  (keyless) modules ignore → ~0 useful events. Low priority, but free, so close it.

**DeHashed**
- **`name:` searches are noise.** A common name returns millions of namesakes; a 1-page
  fetch pulled 100 records, **0** matching the target's confirmed handle. Never trust a
  name-matched record without a second corroborating selector (email/username/phone).
  Prefer email/username/phone pivots; treat name as last resort.
- The page cap is not a hard record cap: a broad `name:` selector reported `pages: 2` /
  100 records under `--max-pages 1`. Budget for more rows than expected on broad selectors.
- A **discovered account on a platform under an ALREADY-KNOWN handle is NOT a new DeHashed
  selector** — same username, already run. It's a manual-review lead, not an autonomous
  pivot. Only a *new* handle / email / phone / hash opens a new DeHashed door. Distinguish
  "new platform for a known handle" (reach) from "new selector" (a door).

**Cross-session / handoff**
- Background job IDs **do not survive a session boundary.** A prior session's "RUNNING IN
  BACKGROUND" scan is gone next session (empty output, no task). **Re-run it** — don't wait
  on it. Verify by checking the output file is non-empty, not by trusting the handoff note.

**Namesake discipline (the biggest trap on a common name)**
- Every name-derived branch in this run resolved to a *different* person. Treat `name:` and
  name-derived-username pivots as **suspect until corroborated**.
- **Cheapest discriminator: age / DOB.** A `dehashed username:matthewmiglio` hit came back
  with DOB `1984-01-19` (~42) for a ~22-year-old target → instantly a different person. Check
  DOB / implied age FIRST on any returned record before believing it.
- **Do NOT fold a namesake's fields into the target case file.** That Wattpad record's email
  (`ride_snow101@hotmail.com`), DOB, IP, and social id belong to someone else — pivoting on
  them investigates the wrong person (out of scope) and poisons the graph. A record counts as
  the target only if it shares a **confirmed** selector (known handle/email/phone) or clear
  linkage — not merely the name.

**gravatar / email-forge**
- `gravatar` on a real, active email often returns **no public profile** (404) — normal, not
  an error.
- `email-forge` emits **guesses**. Checking them against `gravatar` is free, but a hit is
  almost always a stranger (got "Matteo Migliorati" for `miglio@gmail.com`). Only treat a
  gravatar hit as the target if its profile **links to a known handle/account**. **Never spend
  DeHashed credits on email-forge guesses** — verify via free tools first.

**ip-intel**
- Useless on **RFC1918 private IPs** (`10.x`, `192.168.x`, `172.16–31.x`) — they don't
  geolocate. Breaches often store an internal/NAT IP; skip those. And an IP from a *namesake*
  record isn't your target's regardless.

**dossier (finalizer)**
- Reporting sink — emits no new selectors, so it never extends the docket; run it once at the
  end. Only `value` is required per fact; facts with a `date` land on the timeline. The graph
  is provenance-only (source→fact), so keep `source`/`confidence` honest per fact.
