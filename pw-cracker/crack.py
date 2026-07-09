#!/usr/bin/env python3
"""Rainbow-style cracker against rockyou.txt.

Supports:
  * Unsalted: md5, sha1, sha256, sha512  (fast — single inverted pass)
  * Salted slow: bcrypt ($2[aybxy]$...), Django PBKDF2-SHA256 (pbkdf2_sha256$iter$salt$b64hash)

Usage:
  py crack.py <hash> [--algo auto|md5|sha1|sha256|sha512] [--wordlist PATH]
  py crack.py --batch hashes.txt [--wordlist PATH] [--max-slow-words N]
  echo "<hash>" | py crack.py -

Bare-hex hashes are auto-detected by length. DeHashed format "<hex>:salt||ALGO"
or "<hex>:None||ALGO" is honored. Bcrypt and PBKDF2 strings are passed as-is.

Bcrypt + PBKDF2 are SLOW (per-candidate keyed). Cap with --max-slow-words
(default 200k) so a rockyou run doesn't take days. Run a seeded wordlist first.
"""
import sys, hashlib, argparse, os, base64, re, time

# Wordlist ships next to this script; resolve relative so the tool survives being moved.
DEFAULT_WL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rockyou.txt")

ALGO_BY_LEN = {32: 'md5', 40: 'sha1', 64: 'sha256', 128: 'sha512'}
ALGOS = {'md5': hashlib.md5, 'sha1': hashlib.sha1, 'sha256': hashlib.sha256, 'sha512': hashlib.sha512}

BCRYPT_RE = re.compile(r'^\$2[aybxy]\$\d{2}\$[./A-Za-z0-9]{53}$')
DJANGO_PBKDF2_RE = re.compile(r'^pbkdf2_sha256\$(\d+)\$([^\$]+)\$(.+)$')

try:
    import bcrypt as _bcrypt
    HAVE_BCRYPT = True
except ImportError:
    HAVE_BCRYPT = False


def parse_hash(s):
    """Return a dict describing the hash.
    Shapes:
      {'kind':'unsalted', 'algo':..., 'hex':..., 'raw':s}
      {'kind':'salted_simple', 'algo':..., 'hex':..., 'salt':..., 'raw':s}   # pre + post salt sha-family
      {'kind':'bcrypt', 'full':..., 'raw':s}
      {'kind':'pbkdf2_sha256', 'iters':int, 'salt':bytes, 'target':bytes, 'raw':s}
      {'kind':'unknown', 'reason':..., 'raw':s}
    DeHashed-style "<hex>:salt||ALGO" still supported.
    """
    raw = s
    s = s.strip()

    # Strip DeHashed-style ||ALGO suffix if present — it might wrap a $2y$/pbkdf2 string too.
    algo_hint = None
    payload = s
    if '||' in s:
        left, tag = s.rsplit('||', 1)
        tag_l = tag.strip().lower().replace('-', '')
        if tag_l in ALGOS or tag_l in ('blowfish(openbsd)', 'bcrypt', 'django(pbkdf2hmacsha256)'):
            algo_hint = tag_l
            payload = left

    # Bcrypt
    if BCRYPT_RE.match(payload.split(':', 1)[0] if ':' in payload else payload):
        full = payload.split(':', 1)[0] if ':' in payload else payload
        return {'kind': 'bcrypt', 'full': full, 'raw': raw}
    if payload.startswith('$2') and 'bcrypt' in (algo_hint or '') or 'blowfish' in (algo_hint or ''):
        full = payload.split(':', 1)[0]
        return {'kind': 'bcrypt', 'full': full, 'raw': raw}

    # Django pbkdf2_sha256
    m = DJANGO_PBKDF2_RE.match(payload.split(':', 1)[0] if ':' in payload else payload)
    if m:
        try:
            iters = int(m.group(1))
            salt = m.group(2).encode()
            target = base64.b64decode(m.group(3) + '==')
            return {'kind': 'pbkdf2_sha256', 'iters': iters, 'salt': salt, 'target': target, 'raw': raw}
        except Exception as e:
            return {'kind': 'unknown', 'reason': f'pbkdf2 parse: {e}', 'raw': raw}

    # Sha-family (possibly salted via DeHashed colon notation)
    salt = None
    if ':' in payload:
        h, salt = payload.split(':', 1)
        if salt.lower() in ('none', ''):
            salt = None
    else:
        h = payload
    h = h.strip().lower()
    algo = algo_hint if algo_hint in ALGOS else ALGO_BY_LEN.get(len(h))
    if algo not in ALGOS:
        return {'kind': 'unknown', 'reason': f'unknown algo (len={len(h)}, hint={algo_hint})', 'raw': raw}
    if salt:
        return {'kind': 'salted_simple', 'algo': algo, 'hex': h, 'salt': salt, 'raw': raw}
    return {'kind': 'unsalted', 'algo': algo, 'hex': h, 'raw': raw}


def _check_bcrypt(pw_bytes, hash_full):
    try:
        # bcrypt lib needs $2b$ — most variants accepted, but normalize $2y$/$2x$/$2a$ to $2b$ as a fallback
        try:
            return _bcrypt.checkpw(pw_bytes, hash_full.encode())
        except ValueError:
            normalized = '$2b$' + hash_full[4:]
            return _bcrypt.checkpw(pw_bytes, normalized.encode())
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('hash', nargs='?', help='Hash string, or "-" for stdin')
    ap.add_argument('--algo', choices=['auto'] + list(ALGOS), default='auto')
    ap.add_argument('--wordlist', default=DEFAULT_WL)
    ap.add_argument('--batch', help='Path to file containing one hash per line')
    ap.add_argument('--max-slow-words', type=int, default=200000,
                    help='Cap candidates tried against bcrypt/PBKDF2 (default 200k). Use 0 for no cap.')
    args = ap.parse_args()

    if not os.path.exists(args.wordlist):
        print(f'ERROR: wordlist not found: {args.wordlist}', file=sys.stderr)
        sys.exit(2)

    if args.batch:
        with open(args.batch, 'r', encoding='utf-8') as f:
            hashes = [ln.strip() for ln in f if ln.strip() and not ln.startswith('#')]
    elif args.hash == '-':
        hashes = [ln.strip() for ln in sys.stdin if ln.strip()]
    elif args.hash:
        hashes = [args.hash]
    else:
        ap.print_help()
        sys.exit(1)

    forced = None if args.algo == 'auto' else args.algo

    # Bucket targets by kind for efficient pass
    unsalted = {a: {} for a in ALGOS}        # algo -> {hex: raw}
    salted_simple = []                       # (hex, algo, salt, raw)
    bcrypt_targets = []                      # (full_hash, raw)
    pbkdf2_targets = []                      # (iters, salt, target, raw)
    skipped = []

    for raw in hashes:
        info = parse_hash(raw)
        k = info['kind']
        if k == 'unknown':
            skipped.append((raw, info['reason']))
            continue
        if k == 'bcrypt':
            if not HAVE_BCRYPT:
                skipped.append((raw, 'bcrypt module not installed (pip install bcrypt)'))
                continue
            bcrypt_targets.append((info['full'], raw))
            continue
        if k == 'pbkdf2_sha256':
            pbkdf2_targets.append((info['iters'], info['salt'], info['target'], raw))
            continue
        if k == 'salted_simple':
            algo = forced or info['algo']
            salted_simple.append((info['hex'], algo, info['salt'], raw))
            continue
        if k == 'unsalted':
            algo = forced or info['algo']
            unsalted[algo][info['hex']] = raw

    needed_fast = [a for a, d in unsalted.items() if d] + sorted({s[1] for s in salted_simple})
    needed_fast = list(dict.fromkeys(needed_fast))
    total = sum(len(d) for d in unsalted.values()) + len(salted_simple) + len(bcrypt_targets) + len(pbkdf2_targets)

    print(f"Loaded {total} target hashes:")
    print(f"  unsalted: {sum(len(d) for d in unsalted.values())} ({needed_fast})")
    print(f"  salted-simple: {len(salted_simple)}")
    print(f"  bcrypt: {len(bcrypt_targets)} (have bcrypt module: {HAVE_BCRYPT})")
    print(f"  pbkdf2_sha256: {len(pbkdf2_targets)}")
    if skipped:
        print(f"  skipped: {len(skipped)}")
        for raw, why in skipped[:5]:
            print(f"    - {raw[:60]}...  ({why})")
    print(f"Wordlist: {args.wordlist}")
    if (bcrypt_targets or pbkdf2_targets) and args.max_slow_words:
        print(f"Slow algos will stop after {args.max_slow_words:,} candidates (override with --max-slow-words 0)")
    print()

    found = {}   # raw -> (algo, password, line)
    t0 = time.time()
    remaining_unsalted = sum(len(d) for d in unsalted.values())

    with open(args.wordlist, 'rb') as f:
        for i, raw_line in enumerate(f, 1):
            pw = raw_line.rstrip(b'\r\n')
            if not pw:
                continue

            # Fast unsalted path
            for algo in needed_fast:
                if not unsalted[algo]:
                    continue
                h = ALGOS[algo](pw).hexdigest()
                if h in unsalted[algo]:
                    orig = unsalted[algo].pop(h)
                    if orig not in found:
                        try: pw_s = pw.decode('utf-8')
                        except UnicodeDecodeError: pw_s = repr(pw)
                        found[orig] = (algo, pw_s, i)
                        remaining_unsalted -= 1

            # Salted-simple sha-family (pre/post)
            for hex_h, algo, salt, orig in salted_simple:
                if orig in found:
                    continue
                salt_b = salt.encode()
                for cand in (salt_b + pw, pw + salt_b):
                    if ALGOS[algo](cand).hexdigest() == hex_h:
                        try: pw_s = pw.decode('utf-8')
                        except UnicodeDecodeError: pw_s = repr(pw)
                        found[orig] = (algo, pw_s, i)
                        break

            # Slow: bcrypt
            if bcrypt_targets and (not args.max_slow_words or i <= args.max_slow_words):
                for full, orig in bcrypt_targets:
                    if orig in found:
                        continue
                    if _check_bcrypt(pw, full):
                        try: pw_s = pw.decode('utf-8')
                        except UnicodeDecodeError: pw_s = repr(pw)
                        found[orig] = ('bcrypt', pw_s, i)

            # Slow: Django pbkdf2_sha256
            if pbkdf2_targets and (not args.max_slow_words or i <= args.max_slow_words):
                for iters, salt, target, orig in pbkdf2_targets:
                    if orig in found:
                        continue
                    derived = hashlib.pbkdf2_hmac('sha256', pw, salt, iters, dklen=len(target))
                    if derived == target:
                        try: pw_s = pw.decode('utf-8')
                        except UnicodeDecodeError: pw_s = repr(pw)
                        found[orig] = ('pbkdf2_sha256', pw_s, i)

            if i % 100_000 == 0:
                elapsed = time.time() - t0
                rate = i / elapsed if elapsed else 0
                print(f"  ... line {i:>10,}  elapsed {elapsed:6.1f}s  rate {rate:,.0f}/s  hits {len(found)}/{total}")

            # Early exit: all done
            all_slow_done = all(orig in found for _, orig in bcrypt_targets) and \
                            all(orig in found for _, _, _, orig in pbkdf2_targets)
            if remaining_unsalted == 0 and all(s[3] in found for s in salted_simple) and all_slow_done:
                print(f"  All targets cracked at line {i:,} — stopping early")
                break

            # Slow cap reached and only slow remain → stop
            if args.max_slow_words and i > args.max_slow_words:
                only_slow_left = (remaining_unsalted == 0
                                  and all(s[3] in found for s in salted_simple)
                                  and not all_slow_done)
                if only_slow_left:
                    print(f"  Hit --max-slow-words cap ({args.max_slow_words:,}); stopping (slow targets remain).")
                    break

    elapsed = time.time() - t0
    print(f"\nFinished in {elapsed:.1f}s\n")

    hits = 0
    for h in hashes:
        if h in found:
            algo, pw, line = found[h]
            hits += 1
            print(f"[HIT ] {algo:14} {h[:70]:70} -> {pw!r} (line {line:,})")
        else:
            print(f"[MISS] {'?':14} {h[:70]:70} -- not cracked")
    print(f"\n=== Summary: {hits}/{len(hashes)} cracked ===")


if __name__ == '__main__':
    main()
