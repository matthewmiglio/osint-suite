#!/usr/bin/env python
"""wordlist-forge — seed words + dates -> a mutated password wordlist.

Pure stdlib. Takes what you already know about a target (old passwords, pet/kid
names, birth years) and expands each seed with the mutations people actually use:
case flips, light leetspeak, and appended digits/years/symbols. Feed the output
to pw-cracker or hashcat.
"""
import argparse
import sys

LEET = str.maketrans({"a": "@", "e": "3", "i": "1", "o": "0", "s": "$"})
DEFAULT_SUFFIXES = ["", "1", "12", "123", "!", "1!", "123!", "2023", "2024", "2025"]


def case_variants(w):
    return {w, w.lower(), w.upper(), w.capitalize()}


def mutate(seeds, suffixes):
    # ponytail: single-pass leet (one full-substitution variant per word), NOT
    # combinatorial per-char leet -- that explodes O(2^n) for zero real-world gain.
    out, seen = [], set()
    for seed in seeds:
        bases = set()
        for c in case_variants(seed):
            bases.add(c)
            bases.add(c.translate(LEET))
        for base in bases:
            for suf in suffixes:
                word = base + suf
                if word not in seen:
                    seen.add(word)
                    out.append(word)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Expand seed words into a candidate password wordlist.")
    ap.add_argument("seeds", nargs="*", help="Seed words (names, old passwords, etc.)")
    ap.add_argument("--suffix", action="append", default=[],
                    help="Extra suffix to append (repeatable), e.g. a birth year 0804.")
    ap.add_argument("-o", "--out", help="Write to file instead of stdout.")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.seeds:
        ap.error("give at least one seed word (or --selftest)")
    words = mutate(args.seeds, DEFAULT_SUFFIXES + args.suffix)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(words) + "\n")
        print(f"wrote {len(words)} candidates -> {args.out}", file=sys.stderr)
    else:
        print("\n".join(words))
    return 0


def selftest():
    words = mutate(["password"], DEFAULT_SUFFIXES)
    assert "password" in words
    assert "Password123" in words, "case + suffix"
    assert "p@$$w0rd" in words, "leet"
    assert "PASSWORD2025" in words
    assert len(words) == len(set(words)), "dupes"
    assert "password0804" in mutate(["password"], ["0804"]), "custom suffix"
    print("wordlist-forge selftest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
