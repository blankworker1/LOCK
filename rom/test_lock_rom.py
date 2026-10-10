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
    def inputs(self, index=0, store=False, nxt=False, back=False):
        """Set the module's switches (an 11-bit number) and buttons. Inputs are active low."""
        b1, b2 = index & 0xFF, (index >> 8) | (0x80 if store else 0) | (0x40 if nxt else 0) | (0x20 if back else 0)
        self.cmd(f"S {((b1 ^ 0xFF) << 8) | (b2 ^ 0xFF):04x}")
    def lights(self):
        """(the 11 data lights as a list, the same as a number, status byte, block lights A-D as
        4 bits, the unused output). The lights are briefly wrong while the program refreshes
        them, so take two readings half a millisecond apart and wait until they agree."""
        v = int(self.cmd("L").split()[0], 16)
        for _ in range(8):
            self.run_ms(0.5)
            again = int(self.cmd("L").split()[0], 16)
            if again == v: break
            v = again
        return [(v >> (23 - x)) & 1 for x in range(11)], v >> 13, v & 0xFF, (v >> 9) & 15, (v >> 8) & 1
    def press(self, **button):
        self.inputs(0, **button); self.run_ms(110)
        self.inputs(0); self.run_ms(110)
        return self.lights()

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
for case, (idx, bits7) in enumerate(STANDARD[1:] + [random_case() for _ in range(n3)]):
    last, master, body, zpub, desc, qr = reference(idx, bits7)
    m = Machine()
    # the lamp test at power-on: every lamp alone, in order, then all together, then dark
    seq, since, lamp_times = [], 0.0, []
    for step in range(200):
        m.run_ms(100)
        now = int(m.cmd("L").split()[0], 16)
        if not seq or now != seq[-1]:
            if seq: lamp_times.append(since)
            seq.append(now); since = 0.0
        since += 0.1
        if len(seq) > 20 and now == 0: break
    want_seq = [1 << b for b in range(23, -1, -1) if b != 8] + [0xFFFEFF, 0]
    lamp_ok = seq[-len(want_seq):] == want_seq and all(v == 0 for v in seq[:-len(want_seq)])
    lamp_each, lamp_all, lamp_total = lamp_times[-3], lamp_times[-1], (step + 1) * 0.1
    m.run_ms(300)
    entry_ok = undo_ok = True
    for n, value in enumerate(idx + [bits7]):
        if n in (0, 5, 10):             # a wrong entry, then BACK takes it away again (the 12th entry starts the calculation, so it cannot be taken back)
            wrong_value = value ^ 0x55
            m.inputs(wrong_value, store=True); m.run_ms(150); m.inputs(wrong_value); m.run_ms(150)
            undo_ok &= m.lights()[2] == n + 1
            m.inputs(wrong_value, back=True); m.run_ms(150); m.inputs(wrong_value); m.run_ms(150)
            undo_ok &= m.lights()[2] == n
        m.inputs(value); m.run_ms(100)
        data, shown, status, blocks, spare = m.lights()
        entry_ok &= (shown, status, blocks, spare) == (value, n, 0, 0)     # the lights follow the switches
        m.inputs(value, store=True); m.run_ms(150)
        m.inputs(value); m.run_ms(150)
    m.inputs(0)
    total = 0
    for _ in range(40):                 # wait for the result (status: showing the 12th word)
        total += int(m.cmd("T 50000000"))
        data, shown, status, blocks, spare = m.lights()
        if status & 0xC0 == 0x80: break
    word_ok = (shown, status, blocks, spare) == (last, 0x80 | 12, 0, 0)
    wiped = all(not any(m.read(PG[p] * 256, 256)) for p in ("SIO", "D0", "D1", "D2", "IOP", "CIO", "M256"))
    def where(l): return (l[2], l[3])   # (status, block lights)
    ROW1A, ROW41D, WORD = (0xC0 | 1, 8), (0xC0 | 41, 1), (0x80 | 12, 0)
    # BACK: word -> row 41 block D -> C -> B -> A -> row 40 block D; NEXT x5 -> row 41 D; NEXT -> word
    steps = [where(m.press(back=True)) for _ in range(5)] + [where(m.press(nxt=True)) for _ in range(6)]
    back_ok = steps == [ROW41D, (0xC0 | 41, 2), (0xC0 | 41, 4), (0xC0 | 41, 8), (0xC0 | 40, 1),
                        (0xC0 | 41, 8), (0xC0 | 41, 4), (0xC0 | 41, 2), ROW41D, WORD, ROW1A]
    back_ok &= where(m.press(back=True)) == WORD          # from row 1 block A, BACK returns to the word
    rows_ok, wrong, seen = True, 0, []
    for r in range(41):
        row = []
        for b in range(4):
            data, shown, status, blocks, spare = m.press(nxt=True)
            want = (qr[r] + [0, 0, 0])[11 * b:11 * b + 11]
            if data != want or status != (0xC0 | (r + 1)) or blocks != 8 >> b or spare:
                rows_ok = False; wrong += 1
            row += data
        seen.append(row[:41])
    round_ok = where(m.press(nxt=True)) == WORD and m.lights()[1] == last
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
    check(f"{WORDS[idx[0]]} {WORDS[idx[1]]} ... : lamp test {'ok' if lamp_ok else 'WRONG'} "
          f"({lamp_each:.1f} s a lamp, {lamp_all:.1f} s all on, {lamp_total:.0f} s in all), entry {'ok' if entry_ok else 'WRONG'}, "
          f"BACK undoes an entry {'ok' if undo_ok else 'WRONG'}, "
          f"12th word '{WORDS[last]}' {'ok' if word_ok else 'WRONG'}, "
          f"164 blocks {'ok' if rows_ok else f'{wrong} WRONG'}, scan of the lights {scanned}, "
          f"BACK and NEXT steps {'ok' if back_ok else 'WRONG'}, goes round {'ok' if round_ok else 'WRONG'}, "
          f"working memory wiped {'yes' if wiped else 'NO'}; busy for about {total / HZ:.0f} s",
          lamp_ok and entry_ok and undo_ok and word_ok and rows_ok and back_ok and round_ok and wiped)

print("\nALL PASSED" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
