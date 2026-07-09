# wordlist-forge  (Python, stdlib)

Seed words (old passwords, names, dates) → a mutated password wordlist. Expands
each seed with the mutations people actually use: case flips, light leetspeak
(`a→@ e→3 i→1 o→0 s→$`), and appended digits/years/symbols. Feed the output to
`pw-cracker` or hashcat.

```bash
poetry run python wordlist-forge/forge.py fluffy summer --suffix 0804 --suffix 1990 -o wl.txt
poetry run python wordlist-forge/forge.py --selftest    # offline self-check
```

- **Consumes:** known passwords, names, dates
- **Emits:** wordlist (stdout, or `-o file`)
- **Cost:** free, offline
- **Note:** leet is single-pass per word (one substituted variant), not
  combinatorial — deliberate, to avoid an O(2ⁿ) explosion.
