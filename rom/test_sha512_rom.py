#!/usr/bin/env python3
"""Runs the native SHA-512 ROM on the reference CPU model and checks it.
  1. one pass on the published "abc" example
  2. random blocks and states against keycalc.py
  3. a whole 2,048-round seed calculation (4,098 passes), blocks fed in by this script
Reports clock ticks; the real machine runs 6.25 million ticks a second."""
import hashlib, json, os, random, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "reference"))
import keycalc as k
info = json.load(open(os.path.join(here, "sha512.json")))
L = info["labels"]
sim = subprocess.Popen([os.path.join(here, "gtrun"), os.path.join(here, "sha512.rom"), str(L["halt"])],
                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
def cmd(s):
    sim.stdin.write(s + "\n"); sim.stdin.flush()
    return sim.stdout.readline().strip()
HZ = 6.25e6
ticks = int(cmd("R"))
print(f"start-up (tables built): {ticks:,} ticks = {ticks / HZ * 1000:.0f} ms")
cmd(f"W {info['RETLO']} {L['halt'] & 255:02x}{L['halt'] >> 8:02x}")      # return address = halt

def compress(state, block):
    """state: 8 ints, block: 128 bytes -> (new state, ticks)"""
    cmd(f"W {info['H']} " + b"".join(v.to_bytes(8, "little") for v in state).hex())
    cmd(f"W {info['BLOCK']} " + block.hex())
    t = int(cmd(f"G {L['compress']}"))
    out = bytes.fromhex(cmd(f"D {info['H']} 64"))
    return [int.from_bytes(out[8 * i:8 * i + 8], "little") for i in range(8)], t

fails = 0
def check(name, ok):
    global fails
    fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")

blk = b"abc" + b"\x80" + bytes(123) + b"\x18"
st, t = compress(k.H512, blk)
digest = b"".join(v.to_bytes(8, "big") for v in st)
check('published example: SHA-512("abc")', digest == hashlib.sha512(b"abc").digest())
print(f"  one pass: {t:,} ticks = {t / HZ * 1000:.1f} ms")

rng = random.Random(5)
tmin, tmax, good = 10**9, 0, 0
N = 300
for i in range(N):
    state = [rng.getrandbits(64) for _ in range(8)]
    block = bytes(rng.getrandbits(8) for _ in range(128))
    if i < 4:                           # extremes: all zeros, all ones
        state = [0] * 8 if i % 2 == 0 else [2**64 - 1] * 8
        block = bytes(128) if i < 2 else b"\xff" * 128
    got, t = compress(state, block)
    good += got == k._compress(state, block, 64)
    tmin, tmax = min(tmin, t), max(tmax, t)
check(f"{N} random and extreme blocks match keycalc.py", good == N)
print(f"  ticks per pass: {tmin:,} to {tmax:,}")

# the 2,048 rounds for the standard test phrase, exactly as lock.c does them
def hmac_with(pads, msg):
    total = 0
    inner, t = compress(pads[0], msg + b"\x80" + bytes(125 - len(msg)) + ((128 + len(msg)) * 8).to_bytes(2, "big")); total += t
    d = b"".join(v.to_bytes(8, "big") for v in inner)
    outer, t = compress(pads[1], d + b"\x80" + bytes(61) + (192 * 8).to_bytes(2, "big")); total += t
    return b"".join(v.to_bytes(8, "big") for v in outer), total
text = ("abandon " * 11 + "about").encode()
key = text + bytes(128 - len(text))
total = 0
ip, t = compress(k.H512, bytes(b ^ 0x36 for b in key)); total += t
op, t = compress(k.H512, bytes(b ^ 0x5C for b in key)); total += t
u, t = hmac_with((ip, op), b"mnemonic\x00\x00\x00\x01"); total += t
acc = int.from_bytes(u, "big")
for _ in range(2047):
    u, t = hmac_with((ip, op), u); total += t
    acc ^= int.from_bytes(u, "big")
seed = acc.to_bytes(64, "big")
want = hashlib.pbkdf2_hmac("sha512", text, b"mnemonic", 2048)
check("seed after 2,048 rounds (4,098 passes) matches the standard", seed == want)
print(f"  hashing time for the 2,048 rounds: {total:,} ticks = {total / HZ:.1f} seconds")
per_key = total / 4098 * 4114
print(f"  all 4,114 passes of one key: {per_key / HZ:.1f} seconds")
print("\nALL PASSED" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
