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
- **DeHashed costs real money — but run autonomously; do NOT stop to ask.**
  Cap every credit-spending run with `--max-pages 3` (raise only for a selector
  already yielding hits) so spend stays bounded without a human gate. Log the
  planned queries and the remaining balance as you go; report spend at the end.
  Only pause for the user if the balance actually runs out or a run errors.
- **Re-feed recovered passwords back into DeHashed** (`--type password`) to pull
  more leads: a reused password surfaces the target's other accounts. Filter the
  results by a second known selector (email / username / name / IP) and drop
  namesakes before folding anything in. A common numeric or dictionary password
  returns strangers, so cap those (`--max-pages 2`) and corroborate. Keep breach
  dumps and recovered plaintext local otherwise; do not post them elsewhere.

## Core principle — corroborate every identity link (TWO independent ties)
The point of this loop is **not** to pile up selectors. It is to prove that two
profiles/personas belong to the **same real-world entity** — and that requires at
least **two independent ties** between them. One shared selector is a **lead, not a
link.**

- **A single tie is relatively useless.** A shared *handle/username string* is the
  weakest tie of all — handles collide constantly (seen in the wild: `snipesmoney`,
  `chistar`, `sochistar` each returned multiple unrelated people, incl. a whole
  cluster of Russian "Sochi-star" namesakes). Never treat "same handle" as proof
  two accounts are the same person.
- **Two *independent* ties** = two corroborating facts that do **not** both derive
  from the same origin. Examples that confirm a link: shared handle **+** the same
  face photo on both; a confirmed shared **email or phone** **+** a second selector;
  one account self-referencing the other. Two facts that trace to the same single
  source (e.g. one breach row listing a handle and an email together) are **one**
  tie, not two — they only extend the cluster that row already belongs to.
- **Intrinsically-unique selectors are stronger single ties** than a handle (a full
  email address, a phone, a reused *rare* password, a shared password **hash**, a
  matched face/tattoo), but still seek a second before calling a link confirmed.
- **Hops are fine** (A→B→C). But **every hop that joins two distinct personas needs
  its own ≥2 ties.** Confidence does not transfer across an uncorroborated hop: a
  rock-solid internal cluster reached through a single weak tie is still only as
  strong as that one tie.
- **Track links explicitly.** Keep a **links** structure alongside the case file:
  each `(personaA, personaB)` with the list of ties and a confidence
  (`single-tie/unconfirmed`, `corroborated/confirmed`). Report personas as the same
  entity **only at ≥2 independent ties.**
- **Spend discipline follows from this.** When a branch rests on a single tie, the
  next action is to **find a second tie**, NOT to deep-enrich or spend credits down
  that branch. Enriching a single-tie cluster risks profiling the wrong person and
  poisoning the graph with a stranger's data. Fold a discovered cluster into the
  **target** case file only once the link to the target is corroborated; until then
  keep it in a separate *unconfirmed* bucket.

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
| `scrapers/tinder_check` | username | Tinder web-profile validity: **valid** → real name, age, photo URL (new selectors!); else **not_found** | `poetry run python scrapers/tinder_check.py <handle...>` (or `--batch file`, `--selftest`) | free |
| `reverse-image` | image (local file) | candidate names / source profile URLs + a results screenshot — **LEADS**; a face/tattoo match is a strong **second tie** (corroborates a link a shared handle can't) | `poetry run python reverse-image/revimg.py <image>` (headed; solve captcha) | free* |
| `username-enum` | username | profile URLs on sites that have that handle (13 vetted sites) — **LEADS to eyeball**, a handle match is one weak tie | `poetry run python username-enum/username_enum.py <handle>` (`--only`, `--selftest`) | free |
| `gh-user` | username (GitHub) | name, company, location, blog, bio + **commit-author emails** (strong new selectors) | `poetry run python gh-user/gh.py <handle>` (`GITHUB_TOKEN` env raises the rate limit) | free |
| `email-accounts` | email | sites where the email is registered (**LEADS**) — wraps `holehe` | `poetry run python email-accounts/accounts.py <email>` (needs `holehe`) | free |
| `domain-intel` | domain | registrar + created/expiry + nameservers (RDAP), subdomains (crt.sh → `spiderfoot`), A-record IPs (→ `ip-intel`) | `poetry run python domain-intel/domain.py <domain>` (`--no-subs`) | free |
| `exif` | image (local file) | GPS lat/lon (**new location fact**) + camera make/model + timestamps; most social uploads are EXIF-stripped (no-EXIF is normal) | `poetry run python exif/exif_read.py <image...>` (`--gps-only`; needs Pillow) | free |

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
- **ran set** — `(module, selector-value)` pairs already executed; never re-run. For any module
  that writes to a **shared** output dir (notably `dehashed/results/`, which interleaves other
  concurrent/historical investigations), also record the **exact output path** it prints
  (`saved:` / `csv:`) here. Later aggregation (crack-all-hashes, re-pivot passwords, rebuild case
  file) must read **only these recorded paths** — never a glob of the shared dir, and not a date
  glob (concurrent runs share timestamps). See the DeHashed field note.
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
   known password → `dehashed --type password`; **every** username — whether a seed,
   a DeHashed `username`, or a handle SpiderFoot/`scrapers` surfaced — → `username-enum`,
   `gh-user`, the Instagram scraper and `tinder_check`. **Run `tinder_check` and
   `username-enum` on ALL scraped handles, they're free, so none are exempt** (dedupe
   by handle); a domain → `domain-intel` + `spiderfoot`; an IP/phone/email →
   `spiderfoot`; a `name`+`domain` → `email-forge` → candidate emails →
   `gravatar` / `dehashed`; an `email` → `gravatar` + `email-accounts` (surface
   name/username/social profiles + sites the email is registered on); an
   `image`/profile pic → `exif` (GPS/camera/timestamps) + `reverse-image`
   (face/source match = a strong **second tie**); an `ip_address` →
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
- **SF only enumerates accounts for the EMAIL-derived handle**, not for other handles you
  hold. Distinct handles (e.g. `korrart`, `KorrahLeigh` vs the email-local `korrahburns16`)
  are NOT redundant — a username-seeded scan on each surfaced ~10 fresh platform accounts
  (Instagram/TikTok/Redbubble/Picsart/…). Run a username scan for every distinct handle; only
  the handle that *equals* the email local-part is the redundant one.
- **A dotted handle defeats the username scan — SF auto-detects it as a DOMAIN.** A handle like
  `bella.tmz` (dot + tail that looks like a TLD) is seeded as `INTERNET_NAME`/`DOMAIN_NAME`, so SF
  runs domain footprinting (TLD/DNS search) instead of `sfp_accounts` username enumeration — no
  account hits, and if the tail isn't a real TLD the domain scan is empty. There's no CLI flag to
  force seed type. Don't rely on SF for dotted handles; verify them manually
  (`instagram.com/<handle>`, `tiktok.com/@<handle>`, `snapchat.com/add/<handle>`). Given SF's
  account hits are false-positive-prone anyway (a full 13/13 platform run came back all dead ends
  when hand-checked), the manual profile-URL check is the higher-value path for any single handle.

**scrapers/tinder_check (Tinder web-profile validity)**
- `tinder.com/@<handle>` resolves ONLY for handles set to a public web profile. Tinder
  **server-renders** the identifying bits, so a plain `requests` fetch (no browser) tells
  valid from not-found — `poetry run python scrapers/tinder_check.py <handle...>` does this.
- **Verdict keys on personalization, NOT the not-found text.** The "…may have changed their
  ID / Looking for someone" string is baked into the SPA shell for EVERY handle (incl. random
  garbage) and the raw HTML is byte-identical across absent handles — useless as a signal. A
  **valid** page has a personalized `og:title` ("NAME (@handle) | Tinder") + an `og:image` on
  `images-ssl.gotinder.com`; **not_found** has generic `og:title` "Tinder | Dating…" +
  `og:image` `.../static/tinder.png`. (A headless render agrees but is unnecessary.)
- **not_found ≠ not on Tinder.** Public web profiles are opt-in; most active users never
  enable one. Treat not_found as "no public profile for this handle," not proof of absence.
- Known-valid smoke test: `@jdmx` → "JUAN", 38. Use it (or `--selftest`) to sanity-check.
- A **valid** hit yields a real **name + age (+ photo)** — those ARE new selectors: fold them
  in and re-docket (name → dehashed/dossier).
- **Run it on EVERY distinct handle you ever see** — seeds, DeHashed `username` values,
  SpiderFoot `Account on External Site` handles, and handles/names scraped from Instagram or
  Facebook followers/following. It's free, so no handle is exempt — this does NOT inherit the
  DeHashed "known-handle-on-a-new-platform isn't a new selector" rule (that's DeHashed-only).
  Dedupe by handle so each is checked exactly once. Batch them: `tinder_check.py h1 h2 h3 …`.

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
- **Phone format matters — try the country-code prefix.** A US number as bare 10 digits
  (`5862199922`) returned **0** hits; the same number as `15862199922` (leading `1`) returned a
  record. Search the `1`-prefixed E.164-without-`+` form first (or try both); a 0-result bare
  search is NOT proof the phone is absent.
- **`results/` is SHARED — track your own output paths; never glob the dir.** `dehashed/results/`
  accumulates pulls from *every* run: past sessions, selftests, AND **other investigations running
  concurrently right now** (seen in the wild: a second target's runs interleaving the same
  minute, plus its own `dehashed_password_*` feed files). Consequences:
  (1) `results/*.json` folds in total strangers; (2) a `*_<date>_*` or even `*_<date>_<hour>*`
  glob is **NOT** safe either — concurrent runs share the timestamp. The only reliable scope is
  the **exact file paths this run created.** DeHashed prints `saved: <json>` / `csv: <csv>` after
  every query — **record each of those paths into your run log / ran-set as you go**, and when you
  later aggregate (crack every pulled hash, re-pivot cracked passwords, rebuild the case file),
  operate over **that explicit list of paths only**. Treat any record whose file you did not
  personally create this run as out-of-scope.
- **Cracked/plaintext password re-pivot is namesake-gated.** DeHashed returns some `password`
  values already in cleartext and encodes others as `||BASE64` (decode = the plaintext, not a
  hash to crack). Only feed a plaintext back into `--type password` if it is tied to a
  **confirmed** target selector; a password on a *common-handle* row (e.g. an `ALIEN TXTBASE`
  combolist entry under a reused handle) belongs to a namesake, and searching it just enumerates
  strangers. Common passwords are pure noise regardless; a rare/unique one is what makes the
  reuse pivot worthwhile.

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

**pw-cracker / hashes**
- **Crack the target's uncracked hashes early — a cracked password is a real new door**
  (`--type password` reuse pivot). A distinctive plaintext (`9696nick` → 17 users) surfaces the
  target's *other* accounts (found a new email that way); a common one (`nicholas23` → 3852 users)
  is pure noise — search it capped and fold in only rows carrying a known selector.
- **rockyou misses personal-pattern passwords; brute the target's own vocabulary.** A
  DuelingNetwork MD5 that survived rockyou fell in <5s to a targeted set (seed = name/handle/chess
  words × digits/years × leet × symbols). Build that set from the case file before assuming a hash
  is uncrackable.
- **DeHashed's algo label can be a simplification — a "plain SHA-1/MD5" that survives a billion
  candidates is almost certainly salted/layered at the source** (e.g. Zynga 2019). Two Zynga
  `SHA-1` hashes resisted rockyou × ~110 best64 rules + targeted mutations = **1.55B candidates**.
  Set a hard budget (one rockyou+rules pass); if it survives that, mark it a dead end and move on —
  more wordlist is wasted compute, not a better attack.
- **`$6$` sha512-crypt / bcrypt lines are auto-skipped by crack.py and are slow** — they're
  usually namesakes from broad pulls anyway; don't spend the `--max-slow-words` budget on them.

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

**reverse-image (face/photo as a tie)**
- The decisive move for a **two-tie** confirmation when you have a profile photo:
  if the face/tattoo also appears on an account from the other persona, that's a
  strong second tie a shared handle can't give you.
- **A profile avatar is often NOT the account owner's face.** Seen in the wild: a
  Discord "burner" avatar reverse-imaged to a **reposted fitness-influencer photo**
  (Pinterest `@gymbeamgr`/`@strix.fit` pins, a scraper site tagging IG `guedeaoficial`).
  So reverse-image can *disprove* a face-based identity: the picture tied to a random
  influencer, NOT to the handle's other persona → no tie, and the handle match stayed
  an unconfirmed coincidence. Treat "Sites containing this image" as **where the photo
  was reposted**, not as the person.
- Yandex is the engine; it will **captcha** automated runs, so `revimg.py` is **headed**
  and waits for you to solve it. Windows console is cp1252 — the script forces UTF-8 and
  also writes `<out>.json` (non-ASCII result names crash a bare `print`).

**dossier (finalizer)**
- Reporting sink — emits no new selectors, so it never extends the docket; run it once at the
  end. Only `value` is required per fact; facts with a `date` land on the timeline. The graph
  is provenance-only (source→fact), so keep `source`/`confidence` honest per fact.
