#!/usr/bin/env python3
"""Runs the LOCK chip image on the reference CPU model and checks it against keycalc.py.
  1. SHA-256 and RIPEMD-160 on their own
  2. the calculation with inputs and results in memory: 12th word, fingerprint,
     key record, zpub text, descriptor, and every square of the QR code
  3. the whole machine through a model of the plug-in module: words entered on the
     switches, the 12th word and all 41 QR rows read back from the lights
Reports clock ticks; the real machine runs 6.25 million ticks a second.
usage: test_lock_rom.py [random phrases for part 2, default 2] [random phrases for part 3, default 0]"""
import hashlib, json, os, random, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "reference"))
import keycalc as k
info = json.load(open(os.path.join(here, "lock.json")))
L, Zp, PG, OFF = info["labels"], info["Z"], info["pages"], info["off"]
HZ = 6.25e6
HALT = bytes([L["halt"] & 255, L["halt"] >> 8])
WORDS = k.load_words()
fails = 0
def check(name, ok):
    global fails
    fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")

class Machine:
    def __init__(self):
        self.p = subprocess.Popen([os.path.join(here, "gtrun"), os.path.join(here, "lock.rom"), str(L["halt"])],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.cmd("Z")
    def cmd(self, s):
        self.p.stdin.write(s + "\n"); self.p.stdin.flush()
        return self.p.stdout.readline().strip()
    def write(self, addr, data): self.cmd(f"W {addr} {bytes(data).hex()}")
    def read(self, addr, n): return bytes.fromhex(self.cmd(f"D {addr} {n}"))
    def go(self, label): return int(self.cmd(f"G {L[label]}"))
    def run_ms(self, ms): return int(self.cmd(f"T {int(ms * HZ / 1000)}"))
    def inputs(self, index=0, store=False, nxt=False):
        """Set the module's switches (an 11-bit number) and buttons. Inputs are active low."""
        b1, b2 = index & 0xFF, (index >> 8) | (0x80 if store else 0) | (0x40 if nxt else 0)
        self.cmd(f"S {((b1 ^ 0xFF) << 8) | (b2 ^ 0xFF):04x}")
    def lights(self):
        """(41 row lights as a list, first 11 as a number, status byte, the 7 unused outputs).
        The lights are briefly wrong while the program refreshes them (about 0.1 ms in every
        25 ms), so take two readings half a millisecond apart and wait until they agree."""
        v = int(self.cmd("L").split()[0], 16)
        for _ in range(8):
            self.run_ms(0.5)
            again = int(self.cmd("L").split()[0], 16)
            if again == v: break
            v = again
        row = [(v >> (55 - x)) & 1 for x in range(41)]
        return row, v >> 45, v & 0xFF, (v >> 8) & 0x7F

def reference(idx, bits7):
    """The same steps as keycalc.account_key, returning every piece the chip produces."""
    last = k.final_word(idx, bits7)
    phrase = [WORDS[i] for i in idx + [last]]
    seed = k.pbkdf2_sha512(" ".join(phrase).encode(), b"mnemonic", 2048)
    i = k.hmac_sha512(b"Bitcoin seed", seed)
    key, chain = int.from_bytes(i[:32], "big"), i[32:]
    master = k.ripemd160(k.sha256(k.public_key(key)))[:4]
    for depth, step in enumerate((84, 0, 0), 1):
        number = step | 0x80000000
        if depth == 3:
            parent = k.ripemd160(k.sha256(k.public_key(key)))[:4]
        i = k.hmac_sha512(chain, b"\x00" + key.to_bytes(32, "big") + number.to_bytes(4, "big"))
        key, chain = (int.from_bytes(i[:32], "big") + key) % k.N, i[32:]
    body = bytes([3]) + parent + number.to_bytes(4, "big") + chain + k.public_key(key)
    zpub = k.base58check(bytes.fromhex("04B24746") + body)
    assert zpub == k.account_key(phrase)["zpub"]
    desc = f"[{master.hex()}/84h/0h/0h]{zpub}"
    return last, master, body, zpub, desc, k.qr_rows(desc, mask=0)

rng = random.Random(3)
n2 = int(sys.argv[1]) if len(sys.argv) > 1 else 2
n3 = int(sys.argv[2]) if len(sys.argv) > 2 else 0
STANDARD = [([0] * 11, 0), ([1019, 2015, 1790, 2039, 1983, 1533, 2031, 1919, 1019, 2015, 1790], 127)]
def random_case(): return [rng.randrange(2048) for _ in range(11)], rng.randrange(128)

m = Machine()
m.run_ms(100)
print(f"program chip used: {info['words']:,} of 65,536 words ({100 * info['words'] / 65536:.0f}%)")

print("1. small hashes on their own")
good, worst, lengths = 0, 0, [0, 1, 16, 32, 33, 55, 56, 64, 78, 119]
for n in lengths:
    msg = bytes(rng.getrandbits(8) for _ in range(n))
    m.write(PG["M256"] * 256, msg)
    m.write(Zp["S_LEN"], [n]); m.write(OFF["S_TOTAL"], [64 if n < 56 else 128])
    m.write(Zp["S_BH"], [(n * 8) >> 8]); m.write(Zp["S_BL"], [(n * 8) & 255])
    m.write(OFF["R256L"], HALT)
    worst = max(worst, m.go("sha256"))
    good += m.read(OFF["DG"], 32) == hashlib.sha256(msg).digest()
check(f"SHA-256: {good} of {len(lengths)} message lengths correct, up to {worst / HZ * 1000:.0f} ms", good == len(lengths))
good = 0
for _ in range(20):
    msg = bytes(rng.getrandbits(8) for _ in range(32))
    m.write(OFF["DG"], msg); m.write(OFF["RMD_RETL"], HALT)
    ticks = m.go("rmd")
    good += m.read(OFF["FPOUT"], 4) == hashlib.new("ripemd160", msg).digest()[:4]
check(f"RIPEMD-160 (first 4 bytes): {good} of 20 correct, {ticks / HZ * 1000:.0f} ms", good == 20)

print("2. the calculation, inputs and results in memory")
t_calc, t_qr = [], []
for idx, bits7 in STANDARD + [random_case() for _ in range(n2)]:
    m = Machine(); m.run_ms(100)       # a fresh power-up for every key, as on the real machine
    io = PG["IOP"] * 256
    m.write(io + OFF["IDX"], b"".join(i.to_bytes(2, "little") for i in idx) + bytes(2))
    m.write(io + OFF["BITS7"], [bits7])
    m.write(Zp["CALCRETL"], HALT)
    tc = m.go("calc")
    last, master, body, zpub, desc, qr = reference(idx, bits7)
    ok_a = (int.from_bytes(m.read(io + OFF["IDX"] + 22, 2), "little"), m.read(io + OFF["OUT_FP"], 4),
            m.read(io + OFF["BODY"], 74)) == (last, master, body)
    m.write(Zp["QRRETL"], HALT)
    tq = m.go("mkqr")
    got_qr = [[b & 1 for b in m.read((PG["MATRIX"] + y) * 256, 41)] for y in range(41)]
    ok_b = (m.read(PG["B58PG"] * 256 + OFF["ZTXT"], 111).decode("latin1"), m.read(PG["DESCPG"] * 256, 131).decode("latin1"),
            got_qr) == (zpub, desc, qr)
    check(f"{WORDS[idx[0]]} {WORDS[idx[1]]} ... {WORDS[last]}: key {'ok' if ok_a else 'WRONG'}, "
          f"text and QR {'ok' if ok_b else 'WRONG'}; {tc / HZ:.1f} s + {tq / HZ:.2f} s", ok_a and ok_b)
    t_calc.append(tc); t_qr.append(tq)
print(f"  key: {min(t_calc) / HZ:.0f} to {max(t_calc) / HZ:.0f} s; text and QR code: {max(t_qr) / HZ:.2f} s")

print("3. the whole machine, through the plug-in module")
for idx, bits7 in STANDARD[1:] + [random_case() for _ in range(n3)]:
    last, master, body, zpub, desc, qr = reference(idx, bits7)
    m = Machine()
    m.run_ms(100)
    entry_ok = True
    for n, value in enumerate(idx + [bits7]):
        m.inputs(value); m.run_ms(100)
        row, shown, status, pad = m.lights()
        entry_ok &= (shown, status) == (value, n) and not any(row[11:])     # the lights follow the switches
        m.inputs(value, store=True); m.run_ms(150)
        m.inputs(value); m.run_ms(150)
    m.inputs(0)
    total = 0
    for _ in range(40):                 # wait for the result (status: showing the 12th word)
        total += int(m.cmd("T 50000000"))
        row, shown, status, pad = m.lights()
        if status & 0xC0 == 0x80: break
    word_ok = (shown, status) == (last, 0x80 | 12) and not any(row[11:])
    rows_ok, wrong, seen = True, 0, []
    for r in range(41):
        m.inputs(0, nxt=True); m.run_ms(150)
        m.inputs(0); m.run_ms(150)
        row, shown, status, pad = m.lights()
        if row != qr[r] or status != (0xC0 | (r + 1)) or pad:
            rows_ok = False; wrong += 1
        seen.append(row)
    m.inputs(0, nxt=True); m.run_ms(150); m.inputs(0); m.run_ms(150)
    back_ok = m.lights()[2] == (0x80 | 12)
    wiped = all(not any(m.read(PG[p] * 256, 256)) for p in ("SIO", "D0", "D1", "D2", "IOP", "CIO", "M256"))
    scanned = "not tried"
    try:                                # an independent scanner reads the code copied from the lights
        import numpy, zxingcpp
        img = numpy.full((49, 49), 255, numpy.uint8)
        img[4:45, 4:45] = (1 - numpy.array(seen, numpy.uint8)) * 255
        found = zxingcpp.read_barcodes(numpy.kron(img, numpy.ones((8, 8), numpy.uint8)))
        scanned = "ok" if found and found[0].text == desc else "WRONG"
    except ImportError:
        pass
    rows_ok &= scanned != "WRONG"
    check(f"{WORDS[idx[0]]} {WORDS[idx[1]]} ... : entry {'ok' if entry_ok else 'WRONG'}, "
          f"12th word '{WORDS[last]}' {'ok' if word_ok else 'WRONG'}, "
          f"41 rows {'ok' if rows_ok else f'{wrong} WRONG'}, scan of the lights {scanned}, wraps round {'ok' if back_ok else 'WRONG'}, "
          f"working memory wiped {'yes' if wiped else 'NO'}; busy for about {total / HZ:.0f} s",
          entry_ok and word_ok and rows_ok and back_ok and wiped)

print("\nALL PASSED" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
