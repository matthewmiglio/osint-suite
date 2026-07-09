# pw-cracker

Rockyou-style offline hash cracker. Single file: `crack.py`.

**Cracks**
- Unsalted (fast, single inverted pass): `md5`, `sha1`, `sha256`, `sha512`
- Simple-salted sha-family (pre- or post-salt)
- Slow keyed: `bcrypt` (`$2*$`), Django `pbkdf2_sha256$...`

Algo is auto-detected from hash length; DeHashed `<hex>:salt||ALGO` notation is honored.

## Usage
Run inside the shared Poetry env (from the repo root):

```bash
poetry install                       # once, installs bcrypt
poetry run python pw-cracker/crack.py <hash>
poetry run python pw-cracker/crack.py --batch pw-cracker/hashes.txt
echo "<hash>" | poetry run python pw-cracker/crack.py -
```

Flags: `--algo auto|md5|sha1|sha256|sha512`, `--wordlist PATH` (defaults to
`rockyou.txt` next to the script), `--max-slow-words N` (cap candidates tried
against bcrypt/PBKDF2, default 200k; `0` = no cap).

bcrypt and PBKDF2 are per-candidate slow. Run a small seeded wordlist first, or
keep the `--max-slow-words` cap so a full rockyou pass does not run for days.

## Data files (git-ignored)
`rockyou.txt`, `seb_wordlist.txt` (wordlists), `hashes*.txt` (targets),
`cracked_new.txt` / `rows_new.csv` (output). These are excluded by the repo
`.gitignore` because they are large and/or contain cracked plaintext.
