#!/usr/bin/env python3
"""Runs a program that speaks lock.c's input/output against keycalc.py and compares every line.
usage: check_c.py COUNT command...     e.g.  check_c.py 200 ./lock_pc"""
import os, random, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "reference"))
import keycalc as k
words = k.load_words()
count, cmd = int(sys.argv[1]), sys.argv[2:]
rng = random.Random(2026)
cases = [([0] * 11, 0), ([2047] * 11, 127),
         ([1019, 2015, 1790, 2039, 1983, 1533, 2031, 1919, 1019, 2015, 1790], 127)]
cases += [([rng.randrange(2048) for _ in range(11)], rng.randrange(128)) for _ in range(count - len(cases))]
bad = 0
for idx, bits in cases[:count]:
    got = subprocess.run(cmd, input=" ".join(map(str, idx)) + f" {bits}\n", capture_output=True, text=True).stdout
    got = "\n".join(l for l in got.splitlines() if not l.startswith("#"))
    args = [words[i] for i in idx] + [format(bits, "07b"), "--qr"]
    want = subprocess.run([sys.executable, os.path.join(here, "..", "reference", "keycalc.py")] + args,
                          capture_output=True, text=True).stdout.rstrip("\n")
    if got != want:
        bad += 1
        print("MISMATCH", idx, bits)
print(f"{len(cases[:count]) - bad} of {len(cases[:count])} identical to keycalc.py, line for line")
sys.exit(1 if bad else 0)
