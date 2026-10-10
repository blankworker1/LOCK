#!/usr/bin/env python3
"""Runs the native curve ROM on the reference CPU model and checks it.
  1. single operations (multiply, add, subtract, copy) against plain Python arithmetic
  2. whole public keys against keycalc.py
Reports clock ticks; the real machine runs 6.25 million ticks a second.
usage: test_curve_rom.py [number of random keys, default 3]"""
import json, os, random, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "reference"))
import keycalc as k
info = json.load(open(os.path.join(here, "curve.json")))
L, Zp, S, OPS = info["labels"], info["Z"], info["slots"], info["ops"]
sim = subprocess.Popen([os.path.join(here, "gtrun"), os.path.join(here, "curve.rom"), str(L["halt"])],
                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
def cmd(s):
    sim.stdin.write(s + "\n"); sim.stdin.flush()
    return sim.stdout.readline().strip()
HZ = 6.25e6
P, R = k.P, 1 << 256
RINV = pow(R, -1, P)
fails = 0
def check(name, ok):
    global fails
    fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")

t = int(cmd("R"))
print(f"start-up (tables built): {t:,} ticks = {t / HZ * 1000:.0f} ms")

def addr(slot): return S[slot][0] * 256 + S[slot][1]
def put(slot, n): cmd(f"W {addr(slot)} {n.to_bytes(32, 'little').hex()}")
def get(slot): return int.from_bytes(bytes.fromhex(cmd(f"D {addr(slot)} 32")), "little")
def run_op(op, x, y):
    """Put x, y in two slots, run one operation into a third, return (result, ticks)."""
    put("t1", x); put("t2", y)
    page, off = info["SCRATCH"]
    code = bytes([OPS[op], *S["t3"], *S["t1"], *S["t2"], OPS["END"]])
    cmd(f"W {page * 256 + off} {code.hex()}")
    cmd(f"W {Zp['IPP']} {page:02x}"); cmd(f"W {Zp['IPO']} {off:02x}")
    ticks = int(cmd(f"G {L['run_prog']}"))
    return get("t3"), ticks

print("single operations")
rng = random.Random(11)
edge = [0, 1, 2, P - 1, P - 2, (1 << 255), (1 << 256) % P, 0xFF, P >> 1, 977]
pairs = [(x, y) for x in edge for y in edge] + [(rng.randrange(P), rng.randrange(P)) for _ in range(150)]
want = {"MUL": lambda x, y: x * y * RINV % P, "ADD": lambda x, y: (x + y) % P,
        "SUB": lambda x, y: (x - y) % P, "MOV": lambda x, y: x}
for op in ("MUL", "ADD", "SUB", "MOV"):
    good, lo, hi = 0, 10**12, 0
    for x, y in pairs:
        got, ticks = run_op(op, x, y)
        good += got == want[op](x, y)
        lo, hi = min(lo, ticks), max(hi, ticks)
    names = {"MUL": "multiply", "ADD": "add", "SUB": "subtract", "MOV": "copy"}
    check(f"{names[op]}: {good} of {len(pairs)} correct, {lo:,} to {hi:,} ticks ({hi / HZ * 1000:.1f} ms)", good == len(pairs))

print("whole public keys")
count = int(sys.argv[1]) if len(sys.argv) > 1 else 3
keys = [1, 2, 3, k.N - 1, 0x8000000000000000000000000000000000000000000000000000000000000000 % k.N]
keys += [rng.randrange(1, k.N) for _ in range(count)]
total = []
for key in keys:
    cmd(f"W {info['K']} {key.to_bytes(32, 'little').hex()}")
    ticks = int(cmd(f"G {L['pubkey']}"))
    got = bytes.fromhex(cmd(f"D {info['OUT']} 33"))
    ok = got == k.public_key(key)
    label = f"key {key}" if key < 10 else f"key {key:064x}"[:28] + "..."
    check(f"{label}: {ticks:,} ticks = {ticks / HZ:.1f} s", ok)
    if key in keys[5:]: total.append(ticks)
avg = sum(total) / len(total)
print(f"\nrandom keys: {min(total) / HZ:.1f} to {max(total) / HZ:.1f} s, average {avg / HZ:.1f} s; "
      f"the three a LOCK calculation needs: {3 * avg / HZ:.0f} seconds")
print("ALL PASSED" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
