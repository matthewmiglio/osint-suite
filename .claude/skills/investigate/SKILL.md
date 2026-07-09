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
- **DeHashed costs real money.** Before any credit-spending run, state the
  planned queries, confirm with the user, and cap with `--max-pages`. The
  remaining balance prints as it runs; track spend.
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

## Phase 2 — The enrichment loop
Keep two things: the **case file** (facts) and a **ran set** of
`(module, selector)` pairs already executed (so nothing runs twice on the same
input).

Repeat:

**(a) Enumerate modules** — redo Phase 0.

**(b) Build the run plan** — for every module, check each selector it *consumes*
against the *current* case file. A `(module, selector)` is a candidate when we
hold that selector's value AND the pair is not in the ran set. The run plan is
all candidates, each with concrete params.
→ **If the run plan is empty, STOP.** This is the "B yields nothing"
fixpoint: no module can act on anything new.

**(c) Execute the plan** — for each planned run:
- **Programmatic** (`dehashed`, `pw-cracker`, `spiderfoot`): run it. For
  `dehashed`, confirm + cap credits first. Parse the output.
- **Manual** (`scrapers/*`): tell the user exactly how to run it and what to
  paste back; ingest what they return.
- Extract every **new** selector from the output, dedupe against the case file,
  and add it with `source: <module>`. Add each executed pair to the ran set.
- Feed obvious chains immediately: a `hashed_password` from `dehashed` →
  `pw-cracker`; a cracked/known password → a `dehashed --type password` pivot; a
  username → the Instagram scraper; a domain/IP → `spiderfoot`.

Then loop back to (a). If a whole pass produced **no new selectors**, say so, but
keep going only while un-run applicable pairs remain; otherwise stop.

## Phase 3 — Document and report
Whenever the loop stops (or a pass yields nothing), report to the user:
- **New selectors**, grouped by type, each tagged with the module that found it.
- **Run log**: each `(module, input) → result count`.
- **Credits spent** (DeHashed balance delta).
- **Dead ends**: modules/selectors tried with no yield.
- **Suggested manual next steps** the automated loop can't take.

Offer to save the case file + report as a markdown file (git-ignored, e.g. under
an `investigations/` folder) if the user wants it persisted.

## Notes
- The loop converges because each pass either adds a new selector (which may open
  new `(module, selector)` pairs) or adds nothing; once no un-run applicable pair
  remains, it terminates.
- Prefer cheap/free modules first within a pass; save credit-spending DeHashed
  runs for selectors likely to yield, and batch where possible.
