#!/usr/bin/env python3
"""lock_rom.py - the LOCK program chip: the whole machine in one image.

Switches in, lights out:
    11 words and 7 coin-flip bits are entered on the switches
    ->  12th word  ->  words as text  ->  2,048 rounds  ->  master key
    ->  three derivation steps  ->  fingerprints  ->  account public key
    ->  the key as text (zpub)  ->  descriptor  ->  QR code
    ->  the 12th word, then the QR code one row at a time, on the lights

Everything here is native Gigatron code.

Parts, in order of appearance in this file:
    helpers           add with carry, copy, fill, table building
    SHA-512           the heavy hash, written out for speed (from sha512_rom.py)
    curve             256-bit arithmetic and the point formulas (from curve_rom.py)
    SHA-256           small and slow on purpose: one round, run 64 times
    RIPEMD-160        only the first 4 result bytes are needed (the fingerprint)
    glue              keyed hashing, the 2,048-round loop, key derivation
    text and QR       the zpub in base 58, the descriptor, the QR code (fixed mask 0)
    module            the switch and light module on the game controller port
    main              start-up tables, `calc`, `mkqr`, and the entry / display loop

Page zero is shared in time: only one of SHA-512 / curve / SHA-256 /
RIPEMD-160 is running at any moment, and each may use most of it. The few
cells that must survive across them (return addresses, loop counters) live
at 0x6f-0x7f and 0xf9-0xff, which no part touches.
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference"))
import keycalc as k
from gtasm import Asm, imm, zp, IX, yd, YX, AC, IN

a = Asm()
ZERO, ONE = 0x00, 0x80                  # hold 0 and 1: used to turn a top bit into a carry

# ---- RAM pages --------------------------------------------------------------
SIO = 1                                 # SHA-512: state 0x00, block 0x40, digest 0xc0
H5, BLK, DIG = 0x00, 0x40, 0xC0
PAGE_K512 = 2                           # ..6
D0, D1, D2, IOP, CIO = 7, 8, 9, 10, 11
TEXT, BSEED, SALT = 0x00, 0xE0, 0xF0                         # in D0
IPAD, OPAD, TACC, IV512 = 0x00, 0x40, 0x80, 0xC0             # in D1
KEY, IL, NN, NOTN, SA, SB, CHAIN, FPM, FPP = 0x00, 0x20, 0x40, 0x60, 0x81, 0xA2, 0xC3, 0xE3, 0xE7   # in D2
IDX, BITS7, OUT_FP, BODY = 0x00, 0x18, 0x20, 0x30            # in IOP (input/output)
K_OFF, OUT_OFF, SCRATCH_OFF = 0x00, 0x20, 0x80               # in CIO (curve input/output)
PAGE_BC0, PAGE_BC1, PAGE_S0, PAGE_W = 12, 13, 14, 16
PAGE_QT, PAGE_S1N, PAGE_S2N, PAGE_CONST = 17, 18, 19, 20
PAGE_SHR, PAGE_SHL = 23, 32             # shift right by k: page 23+k (k=8: all zero); left by k: 32+k (k=0: unchanged)
PAGE_HN = PAGE_SHR + 4
PAGE_K256, RT_L, RT_R, RT_M, M256 = 40, 42, 43, 44, 45
H256, IV256 = 0x80, 0xA0                # in M256, after the 128-byte message area
PAGE_ML, PAGE_MH, PAGE_ML16, PAGE_MH16 = 48, 64, 80, 96
PAGE_WORDS = 48                         # the word list sits here until the multiply tables replace it
ACC, T = 0x00, 0x40                     # in PAGE_W
B58PG, CHARS, XTPG, DESCPG, QDPG = 21, 22, 41, 46, 47
PAY, ZTXT = 0x00, 0x60                  # in B58PG: the 82-byte key record with checksum; its 111 characters
ALPHA, HEXC, FRAME = 0x00, 0x40, 0x60   # in CHARS: base-58 alphabet, hex digits, the 7-byte light frame
QDATA, ECC0, ECC1 = 0x00, 0x90, 0xA8    # in QDPG: 136 QR data bytes, two sets of 18 check bytes
PAGE_Q58, PAGE_R58, STREAMPG = 112, 116, 120
PAGE_MULG, MATRIX = 89, 48              # 18 check-byte tables; the QR code, one page per row (after the multiply tables are done with)
RS = 0x81                               # 19 page-zero cells for the check-byte sums

# ---- page zero: cells that survive everything ---------------------------------
_pz = list(range(0x6F, 0x80)) + list(range(0xF9, 0x100))
PV = {}
for _n in ("GRETL GRETH G2RETL G2RETH PKRETL PKRETH HK_SP HK_SO HK_LEN PB_LO PB_HI TLEN "
           "CALCRETL CALCRETH QRRETL QRRETH W12LO W12HI").split():
    PV[_n] = _pz.pop(0)
# ---- page zero: SHA-512 ---------------------------------------------------------
STATE, SG, TA, TB, CT, W15 = 0x01, 0x41, 0x49, 0x51, 0x59, 0x61
S5_SUM, LOOP, KPAGE, S5_RETL, S5_RETH = 0x69, 0x6A, 0x6B, 0x6D, 0x6E
def W5(i): return W15 if i % 16 == 15 else 0x81 + 8 * (i % 16)
# ---- page zero: curve ------------------------------------------------------------
A_, B_, LO, HI = 0x01, 0x21, 0x41, 0x81
Z = {}
for _i, _n in enumerate(
        "TMP SUMTMP CSAVE Q NQ NS1 NS2 PLL PHL PLH PHH AP ROWCNT RSRC RIP CNT MTMP "
        "K_FF K_D0 K_03 K_2F K_FC K_FE K_D1 CSP CSO CDP CDO CCNT RET0L RET0H "
        "RET1L RET1H RET2L RET2H RET3L RET3H RETBL RETBH IPP IPO OPC DPG DOF APG AOF BPG BOF "
        "KP KO BYTEI KBYTE MASK STARTED PI_P PI_O PE_P PE_O PS_P PS_O "
        "T1L T1H T2L T2H TDL TDH TA0 TA1 TB0 TB1 TC0 TC1 V0 V1 V2".split()):
    Z[_n] = 0xA1 + _i
assert max(Z.values()) <= 0xEB
# ---- page zero: short-lived cells for the glue (dead whenever a hash or the curve runs)
for _i, _n in enumerate("BITV ACCB BCNT OPTR WP PBRETL PBRETH WPG WOF NLO NHI TI XI HKC HKS HKD".split()):
    Z[_n] = 0x41 + _i
for _i, _n in enumerate("S_LEN S_BH S_BL C2RETL C2RETH FPG FFROM FEND FVAL HRETL HRETH".split()):
    Z[_n] = 0x51 + _i
# ---- page zero: cells for the text, QR and module code (dead whenever a hash or the curve runs)
for _i, _n in enumerate(
        "OPG IOB IOM IOI IOB1 IOB2 IORETL IORETH DLY1 DLY2 DRETL DRETH PRETL PRETH ECHO STAT CNTW BMASK BWANT "
        "BCNT2 UIRETL UIRETH ROWN PKX ZCNT ZRETL ZRETH WLO WHI QP QO QQ QRM B58I B58REM B58N BYTE QPG_ OFFT "
        "Q1 Q2 TMPB PREV QI GPG GV CNT2 MRETL MRETH RSI RSC SI DI QRIGHT QVERT QUP QX QY SPTR SMASK QBIT "
        "QRETL QRETH".split()):
    Z[_n] = 0x01 + _i
assert Z["QRETH"] <= 0x40
FPOUT = 0x5D                            # 4 bytes: where RIPEMD-160 leaves the fingerprint
DG = 0x81                               # 32 bytes: where SHA-256 leaves its result
Z.update(PV)
def v(name): return zp(Z[name])

# =============================================================================
# helpers
# =============================================================================
SUM = [Z["SUMTMP"]]                     # scratch cell used by in-place adds; set per part

def setv(name, val):
    a.ld(val if isinstance(val, tuple) else imm(val)); a.st(v(name))

def call(label, lo, hi=None):
    """Jump to a routine, leaving the way back in two page-zero bytes."""
    if hi is None: lo, hi = Z[lo + "L"], Z[lo + "H"]
    back = f"r{a.pc}"
    a.ld(imm(("lo", back))); a.st(zp(lo))
    a.ld(imm(("hi", back))); a.st(zp(hi))
    a.far(label)
    a.label(back)

def ret(name): a.jump_via(Z[name + "H"], Z[name + "L"])

def far_if_not_zero(label):
    """If AC is not zero, jump (any distance) to label."""
    a.fit(8)
    skip = f"x{a.pc}"
    a.branch("beq", skip); a.nop()
    a.far(label)
    a.label(skip)

def carry(x, y):
    """AC holds x + y (+ carry in), already stored. Sets X so that [X] is the carry out.
    If the sum's top bit is 1 the carry is (x AND y), otherwise (x OR y)."""
    keep = a.y
    a.fit(6)
    neg, join = f"n{a.pc}", f"j{a.pc}"
    a.branch("blt", neg)
    a.ld(x)                             # (runs either way)
    a.branch("bra", join)
    a.ora(y)
    a.label(neg); a.y = keep
    a.anda(y)
    a.label(join); a.y = keep
    a.anda(imm(0x80), "X")              # X = 0x00 or 0x80

def add(dst, x, y, cin=0, cout=False):
    """dst = x + y over lists of byte operands, lowest first.
    cin: 0, 1, or "ac" (carry already in AC). cout: leave the final carry in AC.
    Subtraction is done as x + (not y) + 1."""
    inplace = dst[0] == x[0]
    for j in range(len(dst)):
        if j: a.adda(x[j])
        elif cin == 0: a.ld(x[0])
        elif cin == 1: a.ld(imm(1)); a.adda(x[0])
        else: a.adda(x[0])
        a.adda(y[j])
        if j == len(dst) - 1 and not cout:
            a.st(dst[j]); break
        a.st(zp(SUM[0]) if inplace else dst[j])
        carry(x[j], y[j])
        if inplace:
            a.ld(zp(SUM[0])); a.st(dst[j])
        a.ld(IX)                        # AC = memory[0x00] = 0 or memory[0x80] = 1

def zw(base, n): return [zp(base + j) for j in range(n)]
def yw(base, n): return [yd(base + j) for j in range(n)]

def sigma(dst, src, terms, n):
    """dst = XOR of rotations/shifts of the n-byte word at src (page zero), by table lookup."""
    for j in range(n):
        parts = []
        for kind, amount in terms:
            q, s = divmod(amount, 8)
            for m, page in ((j + q, PAGE_SHR + s if s else None), (j + q + 1, PAGE_SHL + 8 - s if s else "skip")):
                if page == "skip" or (kind == "shr" and m > n - 1):
                    continue
                parts.append((m % n, page))
        parts.sort(key=lambda p: (p[1] is not None, p[1] or 0), reverse=bool(j & 1))
        first = True
        for m, page in parts:
            op = a.ld if first else a.xora
            if page is None: op(zp(src + m))
            else:
                a.ld(zp(src + m), "X"); a.page(page); op(YX)
            first = False
        a.st(zp(dst + j))

def table_loop(body, count=256):
    """Run body() with CNT = 0..count-1."""
    setv("CNT", 0)
    a.fit(120)
    top = f"t{a.pc}"
    a.label(top)
    body()
    a.ld(v("CNT")); a.adda(imm(1)); a.st(v("CNT"))
    if count != 256: a.xora(imm(count))
    a.branch("bne", top); a.nop()

def poke(page, off, data):
    """Write constant bytes into RAM."""
    a.ld(imm(page), "Y"); a.ld(imm(off), "X")
    for b in data: a.sti(b)

def copy(sp, so, dp, do, n=32, reverse=False):
    """n bytes from (page sp, offset so) to (page dp, offset do). reverse: last byte first."""
    setv("CSP", sp); setv("CSO", so); setv("CDP", dp)
    setv("CDO", do + n - 1 if reverse else do); setv("CCNT", n)
    call("copyrev" if reverse else "copyn", "RET0")

def fill(page, start, end, value=0):
    """Set bytes start..end-1 of a page to value."""
    setv("FPG", page); setv("FFROM", start); setv("FEND", end); setv("FVAL", value)
    call("fill", "RET0")

def routines_helpers():
    for name, step in (("copyn", 1), ("copyrev", -1)):
        a.label(name)
        a.fit(24)
        top = f"t{a.pc}"
        a.label(top)
        a.ld(v("CSO"), "X"); a.ld(v("CSP"), "Y"); a.ld(YX)
        a.ld(v("CDO"), "X"); a.ld(v("CDP"), "Y"); a.st(YX)
        a.ld(v("CSO")); a.adda(imm(1)); a.st(v("CSO"))
        a.ld(v("CDO")); (a.adda if step > 0 else a.suba)(imm(1)); a.st(v("CDO"))
        a.ld(v("CCNT")); a.suba(imm(1)); a.st(v("CCNT"))
        a.branch("bne", top); a.nop()
        ret("RET0")
    a.label("fill")
    a.fit(20)
    a.label("fl")
    a.ld(v("FFROM")); a.xora(v("FEND"))
    a.branch("beq", "fl_done")
    a.ld(v("FFROM"), "X")
    a.ld(v("FPG"), "Y"); a.ld(v("FVAL")); a.st(YX)
    a.ld(v("FFROM")); a.adda(imm(1)); a.st(v("FFROM"))
    a.branch("bra", "fl"); a.nop()
    a.label("fl_done")
    ret("RET0")

# =============================================================================
# SHA-512: one pass over the block at SIO.BLK, state at SIO.H5
# =============================================================================
def routines_sha512():
    SUM[0] = S5_SUM
    def round_(r):
        s = lambda j: STATE + 8 * ((j - r) % 8)
        A, B, C, D, E, F, G, H = (s(j) for j in range(8))
        sigma(SG, E, [("rot", 14), ("rot", 18), ("rot", 41)], 8)
        add(zw(TA, 8), zw(H, 8), zw(SG, 8))
        for j in range(8):
            a.ld(zp(F + j)); a.xora(zp(G + j)); a.anda(zp(E + j)); a.xora(zp(G + j)); a.st(zp(CT + j))
        add(zw(TB, 8), zw(TA, 8), zw(CT, 8))
        a.ld(zp(KPAGE), "Y")
        add(zw(TA, 8), zw(TB, 8), yw(8 * r, 8))
        add(zw(TB, 8), zw(TA, 8), zw(W5(r), 8))
        sigma(SG, A, [("rot", 28), ("rot", 34), ("rot", 39)], 8)
        for j in range(8):
            a.ld(zp(B + j)); a.xora(zp(C + j)); a.st(zp(S5_SUM))
            a.ld(zp(A + j)); a.xora(zp(B + j)); a.anda(zp(S5_SUM)); a.xora(zp(B + j)); a.st(zp(CT + j))
        add(zw(TA, 8), zw(SG, 8), zw(CT, 8))
        add(zw(D, 8), zw(D, 8), zw(TB, 8))
        add(zw(H, 8), zw(TB, 8), zw(TA, 8))
    def schedule(r):
        sigma(SG, W5(r + 1), [("rot", 1), ("rot", 8), ("shr", 7)], 8)
        add(zw(TA, 8), zw(W5(r), 8), zw(SG, 8))
        sigma(SG, W5(r + 14), [("rot", 19), ("rot", 61), ("shr", 6)], 8)
        add(zw(TB, 8), zw(TA, 8), zw(W5(r + 9), 8))
        add(zw(W5(r), 8), zw(TB, 8), zw(SG, 8))
    a.label("compress")
    a.page(SIO)
    for i in range(8):
        for j in range(8):
            a.ld(yd(H5 + 8 * i + j)); a.st(zp(STATE + 8 * i + j))
    for i in range(16):
        for j in range(8):
            a.ld(yd(BLK + 8 * i + 7 - j)); a.st(zp(W5(i) + j))
    a.ld(imm(0)); a.st(zp(LOOP)); a.ld(imm(PAGE_K512)); a.st(zp(KPAGE))
    a.label("cycle")
    for r in range(16):
        a.fit(7)
        a.ld(zp(LOOP))
        a.branch("bne", f"sched{r}"); a.nop()
        a.far(f"round{r}")
        a.label(f"sched{r}")
        schedule(r)
        a.label(f"round{r}")
        round_(r)
    a.ld(zp(KPAGE)); a.adda(imm(1)); a.st(zp(KPAGE))
    a.ld(zp(LOOP)); a.adda(imm(1)); a.st(zp(LOOP))
    a.fit(7)
    a.xora(imm(5))
    a.branch("beq", "finish"); a.nop()
    a.far("cycle")
    a.label("finish")
    a.page(SIO)
    for i in range(8):
        add(yw(H5 + 8 * i, 8), yw(H5 + 8 * i, 8), zw(STATE + 8 * i, 8))
    a.jump_via(S5_RETH, S5_RETL)
    # digest: the state as bytes, highest first
    a.label("h2dig")
    a.page(SIO)
    for i in range(8):
        for m in range(8):
            a.ld(yd(H5 + 8 * i + 7 - m)); a.st(yd(DIG + 8 * i + m))
    ret("HRET")
    # block = the 64 digest bytes, padded as the second block of a keyed hash
    a.label("dig2blk")
    a.page(SIO)
    for i in range(64):
        a.ld(yd(DIG + i)); a.st(yd(BLK + i))
    a.ld(imm(0x80)); a.st(yd(BLK + 64))
    a.ld(imm(0))
    for i in range(65, 126): a.st(yd(BLK + i))
    a.st(yd(BLK + 127))
    a.ld(imm(6)); a.st(yd(BLK + 126))  # 192 bytes = 1536 bits = 0x0600
    ret("HRET")

def compress512(): call("compress", S5_RETL, S5_RETH)

# =============================================================================
# curve: 256-bit arithmetic modulo the prime, point formulas, public key
# =============================================================================
SLOTS = "PX PY PZ t1 t2 t3 t4 t5 t6 GX GY ONEM ONE1 IA IR X1".split()
def slot(name):
    s = SLOTS.index(name)
    return PAGE_S0 + s // 8, (s % 8) * 32
END, MUL, ADD, SUB, MOV = 0, 1, 2, 3, 4
PROGRAMS = {
    "DOUBLE": [
        (MUL, "t1", "PX", "PX"), (MUL, "t2", "PY", "PY"), (MUL, "t3", "t2", "t2"),
        (ADD, "t4", "PX", "t2"), (MUL, "t4", "t4", "t4"), (SUB, "t4", "t4", "t1"),
        (SUB, "t4", "t4", "t3"), (ADD, "t4", "t4", "t4"),
        (ADD, "t5", "t1", "t1"), (ADD, "t5", "t5", "t1"), (MUL, "t6", "t5", "t5"),
        (MUL, "PZ", "PY", "PZ"), (ADD, "PZ", "PZ", "PZ"),
        (SUB, "PX", "t6", "t4"), (SUB, "PX", "PX", "t4"),
        (SUB, "t4", "t4", "PX"), (MUL, "t4", "t5", "t4"),
        (ADD, "t3", "t3", "t3"), (ADD, "t3", "t3", "t3"), (ADD, "t3", "t3", "t3"),
        (SUB, "PY", "t4", "t3")],
    "ADDG": [
        (MUL, "t1", "PZ", "PZ"), (MUL, "t2", "GX", "t1"), (SUB, "t2", "t2", "PX"),
        (MUL, "t3", "PZ", "t1"), (MUL, "t3", "GY", "t3"), (SUB, "t3", "t3", "PY"),
        (MUL, "t4", "t2", "t2"), (MUL, "t5", "t2", "t4"), (MUL, "t4", "PX", "t4"),
        (MUL, "t6", "t3", "t3"), (SUB, "t6", "t6", "t5"), (SUB, "t6", "t6", "t4"), (SUB, "t6", "t6", "t4"),
        (SUB, "t4", "t4", "t6"), (MUL, "t4", "t3", "t4"),
        (MUL, "t5", "PY", "t5"), (SUB, "PY", "t4", "t5"),
        (MUL, "PZ", "PZ", "t2"), (MOV, "PX", "t6", "t6")],
    "INITG": [(MOV, "PX", "GX", "GX"), (MOV, "PY", "GY", "GY"), (MOV, "PZ", "ONEM", "ONEM")],
    "PRE_INV": [(MOV, "IA", "PZ", "PZ")],
    "INV_INIT": [(MOV, "IR", "IA", "IA")],
    "INV_SQR": [(MUL, "IR", "IR", "IR")],
    "INV_MUL": [(MUL, "IR", "IR", "IA")],
    "FINAL": [
        (MUL, "t2", "IR", "IR"), (MUL, "PX", "PX", "t2"),
        (MUL, "t2", "IR", "t2"), (MUL, "PY", "PY", "t2"),
        (MUL, "PX", "PX", "ONE1"), (MUL, "PY", "PY", "ONE1")],
}
PROG_AT, bc = {}, {PAGE_BC0: bytearray(), PAGE_BC1: bytearray()}
for _name, _steps in PROGRAMS.items():
    _code = bytearray()
    for _op, _d, _x, _y in _steps:
        _code += bytes([_op, *slot(_d), *slot(_x), *slot(_y)])
    _code.append(END)
    _page = PAGE_BC0 if len(bc[PAGE_BC0]) + len(_code) <= 256 else PAGE_BC1
    assert len(bc[_page]) + len(_code) <= 256
    PROG_AT[_name] = (_page, len(bc[_page]))
    bc[_page] += _code

def run(name):
    setv("IPP", PROG_AT[name][0]); setv("IPO", PROG_AT[name][1])
    call("interp", "RET2")

def curve_cells():
    """The curve code's constant cells. Other parts overwrite them, so set before each use."""
    for name, val in (("K_FF", 0xFF), ("K_D0", 0xD0), ("K_03", 0x03), ("K_2F", 0x2F),
                      ("K_FC", 0xFC), ("K_FE", 0xFE), ("K_D1", 0xD1)):
        setv(name, val)

def init_curve_small():
    """q table, subtraction tables, constants and programs: built once at start-up."""
    SUM[0] = Z["SUMTMP"]
    curve_cells()
    setv("V0", 0)
    def qtable():
        a.ld(v("CNT"), "X"); a.page(PAGE_QT); a.ld(v("V0")); a.st(YX)
        a.adda(imm(0x31)); a.st(v("V0"))
    table_loop(qtable)
    setv("V0", 0); a.st(v("V1")); a.st(v("V2"))
    def stable():
        a.ld(v("CNT"), "X")
        a.page(PAGE_S1N); a.ld(v("V1")); a.xora(imm(0xFF)); a.st(YX)
        a.page(PAGE_S2N); a.ld(v("V2")); a.xora(imm(0xFF)); a.st(YX)
        add([v("V0"), v("V1"), v("V2")], [v("V0"), v("V1"), v("V2")], [v("K_D1"), v("K_03"), zp(ZERO)])
    table_loop(stable)
    R = 1 << 256
    for name, val in (("GX", k.GX * R % k.P), ("GY", k.GY * R % k.P), ("ONEM", R % k.P), ("ONE1", 1)):
        poke(*slot(name), val.to_bytes(32, "little"))
    poke(PAGE_CONST, 0, (k.P - 2).to_bytes(32, "little"))
    for page, code in bc.items():
        poke(page, 0, code)

def init_mul_tables():
    """Entry x of table n holds n*x (low-byte page, high-byte page); also 16n*x."""
    SUM[0] = Z["SUMTMP"]
    def zero_and_identity():
        a.ld(v("CNT"), "X")
        a.ld(imm(0))
        for page in (PAGE_ML, PAGE_MH, PAGE_MH + 1, PAGE_ML16, PAGE_MH16):
            a.ld(imm(page), "Y"); a.st(YX)
        a.ld(imm(PAGE_ML + 1), "Y"); a.ld(v("CNT")); a.st(YX)
    table_loop(zero_and_identity)
    def table_add(dl, dh, s1l, s1h, s2l, s2h):
        for name, page in (("TDL", dl), ("TDH", dh), ("T1L", s1l), ("T1H", s1h), ("T2L", s2l), ("T2H", s2h)):
            setv(name, page)
        call("tadd", "RET0")
    for n in range(2, 16):
        table_add(PAGE_ML + n, PAGE_MH + n, PAGE_ML + n - 1, PAGE_MH + n - 1, PAGE_ML + 1, PAGE_MH + 1)
    table_add(PAGE_ML16 + 1, PAGE_MH16 + 1, PAGE_ML + 15, PAGE_MH + 15, PAGE_ML + 1, PAGE_MH + 1)
    for n in range(2, 16):
        table_add(PAGE_ML16 + n, PAGE_MH16 + n, PAGE_ML16 + n - 1, PAGE_MH16 + n - 1, PAGE_ML16 + 1, PAGE_MH16 + 1)

def routines_curve():
    SUM[0] = Z["SUMTMP"]
    a.label("tadd")
    def tadd_body():
        a.ld(v("CNT"), "X")
        for src, dst in (("T1L", "TA0"), ("T1H", "TA1"), ("T2L", "TB0"), ("T2H", "TB1")):
            a.ld(v(src), "Y"); a.ld(YX); a.st(v(dst))
        add([v("TC0"), v("TC1")], [v("TA0"), v("TA1")], [v("TB0"), v("TB1")])
        a.ld(v("CNT"), "X")
        a.ld(v("TDL"), "Y"); a.ld(v("TC0")); a.st(YX)
        a.ld(v("TDH"), "Y"); a.ld(v("TC1")); a.st(YX)
    table_loop(tadd_body)
    ret("RET0")

    # fe_mul: working value = A * B / 2^256 mod prime (A, B in page zero)
    a.label("fe_mul")
    a.page(PAGE_W); a.ld(imm(0))
    for j in range(33): a.st(yd(ACC + j))
    setv("AP", A_); setv("ROWCNT", 32)
    a.label("row")
    a.ld(v("AP"), "X"); a.ld(IX); a.st(v("MTMP"))
    a.anda(imm(15)); a.adda(imm(PAGE_ML)); a.st(v("PLL"))
    a.ld(v("MTMP")); a.anda(imm(15)); a.adda(imm(PAGE_MH)); a.st(v("PHL"))
    a.ld(v("MTMP"), "X"); a.page(PAGE_HN)
    a.ld(YX); a.adda(imm(PAGE_ML16)); a.st(v("PLH"))
    a.ld(YX); a.adda(imm(PAGE_MH16)); a.st(v("PHH"))
    for j in range(32):
        a.ld(zp(B_ + j), "X")
        a.ld(v("PLL"), "Y"); a.ld(YX); a.st(v("TMP"))
        a.ld(v("PLH"), "Y"); a.adda(YX); a.st(zp(LO + j))
        carry(v("TMP"), YX); a.ld(IX)
        a.ld(zp(B_ + j), "X")
        a.ld(v("PHL"), "Y"); a.adda(YX)
        a.ld(v("PHH"), "Y"); a.adda(YX); a.st(zp(HI + j))
    a.page(PAGE_W)
    add([yd(T)], [yd(ACC)], [zp(LO)], cout=True)
    a.st(v("CSAVE"))
    a.ld(yd(T)); a.ld(AC, "X")
    a.page(PAGE_QT); a.ld(YX); a.st(v("Q")); a.ld(AC, "X")
    a.xora(imm(0xFF)); a.st(v("NQ"))
    a.page(PAGE_S1N); a.ld(YX); a.st(v("NS1"))
    a.page(PAGE_S2N); a.ld(YX); a.st(v("NS2"))
    a.page(PAGE_W); a.ld(v("CSAVE"))
    add(yw(T + 1, 31), yw(ACC + 1, 31), zw(LO + 1, 31), cin="ac", cout=True)
    a.adda(yd(ACC + 32)); a.st(v("TMP")); a.adda(v("Q")); a.st(yd(T + 32))
    carry(v("TMP"), v("Q")); a.ld(IX); a.st(yd(T + 33))
    add(yw(ACC, 32), yw(T + 1, 32), zw(HI, 32), cout=True)
    a.adda(yd(T + 33)); a.st(yd(ACC + 32))
    add(yw(ACC, 5), yw(ACC, 5), [v("NS1"), v("NS2"), v("K_FF"), v("NQ"), v("K_FF")], cin=1, cout=True)
    a.fit(24)
    a.branch("bne", "rip_done")
    a.ld(imm(ACC + 5))
    a.st(v("RIP"))
    a.label("rip"); a.y = PAGE_W
    a.ld(v("RIP"), "X"); a.ld(YX)
    a.branch("beq", "rip_zero")
    a.suba(imm(1))
    a.st(YX)
    a.branch("bra", "rip_done"); a.nop()
    a.label("rip_zero"); a.y = PAGE_W
    a.st(YX)
    a.ld(v("RIP")); a.adda(imm(1)); a.st(v("RIP"))
    a.branch("bra", "rip"); a.nop()
    a.label("rip_done"); a.y = PAGE_W
    a.ld(v("AP")); a.adda(imm(1)); a.st(v("AP"))
    a.ld(v("ROWCNT")); a.suba(imm(1)); a.st(v("ROWCNT"))
    a.fit(8)
    a.branch("beq", "fe_tail"); a.nop()
    a.far("row")
    a.label("fe_tail")
    a.page(PAGE_W)
    NOT_P = [v("K_D0"), v("K_03"), zp(ZERO), zp(ZERO), zp(ONE)] + [zp(ZERO)] * 27 + [v("K_FF")]
    add(yw(T, 33), yw(ACC, 33), NOT_P, cin=1, cout=True)
    a.fit(6)
    a.branch("beq", "tail_sel")
    a.ld(imm(ACC))
    a.ld(imm(T))
    a.label("tail_sel")
    a.st(v("RSRC"))
    ret("RET1")

    a.label("fe_add")
    a.page(PAGE_W)
    add(yw(ACC, 32), zw(A_, 32), zw(B_, 32), cout=True)
    a.st(yd(ACC + 32))
    a.far("fe_tail")

    a.label("fe_sub")
    for j in range(32):
        a.ld(zp(B_ + j)); a.xora(imm(0xFF)); a.st(zp(LO + j))
    a.page(PAGE_W)
    add(yw(ACC, 32), zw(A_, 32), zw(LO, 32), cin=1, cout=True)
    a.st(v("CSAVE"))
    P_BYTES = [v("K_2F"), v("K_FC"), v("K_FF"), v("K_FF"), v("K_FE")] + [v("K_FF")] * 27
    add(yw(T, 32), yw(ACC, 32), P_BYTES)
    a.ld(v("CSAVE"))
    a.fit(6)
    a.branch("beq", "sub_sel")
    a.ld(imm(T))
    a.ld(imm(ACC))
    a.label("sub_sel")
    a.st(v("RSRC"))
    ret("RET1")

    # interp: run a program of (operation, result, x, y) steps
    a.label("interp")
    for t in range(7):
        if t == 0: a.ld(v("IPO"), "X")
        else: a.ld(v("IPO")); a.adda(imm(t)); a.ld(AC, "X")
        a.ld(v("IPP"), "Y"); a.ld(YX); a.st(zp(Z["OPC"] + t))
    a.ld(v("IPO")); a.adda(imm(7)); a.st(v("IPO"))
    a.ld(v("OPC"))
    a.fit(8)
    a.branch("bne", "i_notend"); a.nop()
    ret("RET2")
    a.label("i_notend")
    a.ld(v("OPC")); a.xora(imm(MOV))
    a.fit(8)
    a.branch("bne", "i_op"); a.nop()
    a.far("i_mov")
    a.label("i_op")
    copy(v("APG"), v("AOF"), 0, A_)
    copy(v("BPG"), v("BOF"), 0, B_)
    a.ld(imm(("lo", "i_store"))); a.st(v("RET1L")); a.ld(imm(("hi", "i_store"))); a.st(v("RET1H"))
    a.ld(v("OPC")); a.xora(imm(MUL))
    a.fit(8)
    a.branch("bne", "i_n1"); a.nop()
    a.far("fe_mul")
    a.label("i_n1")
    a.ld(v("OPC")); a.xora(imm(ADD))
    a.fit(8)
    a.branch("bne", "i_n2"); a.nop()
    a.far("fe_add")
    a.label("i_n2")
    a.far("fe_sub")
    a.label("i_store")
    setv("CSP", PAGE_W); setv("CSO", v("RSRC")); setv("CDP", v("DPG")); setv("CDO", v("DOF")); setv("CCNT", 32)
    call("copyn", "RET0")
    a.far("interp")
    a.label("i_mov")
    setv("CSP", v("APG")); setv("CSO", v("AOF")); setv("CDP", v("DPG")); setv("CDO", v("DOF")); setv("CCNT", 32)
    call("copyn", "RET0")
    a.far("interp")

    # bitloop: walk a 256-bit number from the top bit down
    def runv(prefix):
        a.ld(v(prefix + "_P")); a.st(v("IPP")); a.ld(v(prefix + "_O")); a.st(v("IPO"))
        call("interp", "RET2")
    a.label("bitloop")
    setv("STARTED", 0); setv("BYTEI", 31)
    a.label("bl_byte")
    a.ld(v("KO")); a.adda(v("BYTEI")); a.ld(AC, "X"); a.ld(v("KP"), "Y"); a.ld(YX); a.st(v("KBYTE"))
    for mask in (128, 64, 32, 16, 8, 4, 2, 1):
        setv("MASK", mask); call("process_bit", "RETB")
    a.ld(v("BYTEI")); a.suba(imm(1)); a.st(v("BYTEI"))
    a.fit(8)
    a.branch("blt", "bl_done"); a.nop()
    a.far("bl_byte")
    a.label("bl_done")
    ret("RET3")
    a.label("process_bit")
    a.ld(v("STARTED"))
    a.fit(8)
    a.branch("bne", "pb_every"); a.nop()
    a.far("pb_test")
    a.label("pb_every")
    runv("PE")
    a.label("pb_test")
    a.ld(v("KBYTE")); a.anda(v("MASK"))
    a.fit(8)
    a.branch("bne", "pb_set"); a.nop()
    ret("RETB")
    a.label("pb_set")
    a.ld(v("STARTED"))
    a.fit(24)
    a.branch("bne", "pb_add"); a.nop()
    setv("STARTED", 1)
    runv("PI")
    ret("RETB")
    a.label("pb_add")
    runv("PS")
    ret("RETB")

    def set_programs(first, every, when_set):
        for prefix, name in (("PI", first), ("PE", every), ("PS", when_set)):
            setv(prefix + "_P", PROG_AT[name][0]); setv(prefix + "_O", PROG_AT[name][1])

    # pubkey: 32-byte key at CIO.K (lowest byte first) -> 33 bytes at CIO.OUT
    a.label("pubkey")
    curve_cells()
    setv("KP", CIO); setv("KO", K_OFF)
    set_programs("INITG", "DOUBLE", "ADDG")
    call("bitloop", "RET3")
    run("PRE_INV")
    setv("KP", PAGE_CONST); setv("KO", 0)
    set_programs("INV_INIT", "INV_SQR", "INV_MUL")
    call("bitloop", "RET3")
    run("FINAL")
    px, py = slot("PX"), slot("PY")
    a.page(px[0])
    a.ld(yd(py[1])); a.anda(imm(1)); a.adda(imm(2)); a.st(v("TMP"))
    for i in range(32):
        a.ld(yd(px[1] + 31 - i)); a.st(zp(A_ + i))
    a.page(CIO)
    a.ld(v("TMP")); a.st(yd(OUT_OFF))
    for i in range(32):
        a.ld(zp(A_ + i)); a.st(yd(OUT_OFF + 1 + i))
    ret("PKRET")

# =============================================================================
# SHA-256: message at M256 (up to 119 bytes), result as 32 bytes at page zero DG
# =============================================================================
RA256, SG2, TA2, TB2, CT2, KW2, WW2 = 0x01, 0x21, 0x25, 0x29, 0x2D, 0x31, 0x35
TCNT, WIDX, KIDX, S2_SUM, S_TOTAL, R256L, R256H = 0x39, 0x3A, 0x3B, 0x3C, 0x3D, 0x3E, 0x3F
XA, XB, XC, XD = 0x41, 0x45, 0x49, 0x4D
WZ = 0x81                               # 16 message words, lowest byte first

def routines_sha256():
    SUM[0] = S2_SUM
    A, B, C, D, E, F, G, H = (RA256 + 4 * i for i in range(8))
    def wfetch(dst, ahead):             # dst = w[(t + ahead) mod 16]
        for j in range(4):
            a.ld(zp(WIDX)); a.adda(imm(4 * ahead + j)); a.anda(imm(63)); a.adda(imm(WZ)); a.ld(AC, "X")
            a.ld(IX); a.st(zp(dst + j))
    a.label("c256")                     # one pass over M256[0..63]
    a.page(M256)
    for i in range(16):
        for j in range(4):
            a.ld(yd(4 * i + 3 - j)); a.st(zp(WZ + 4 * i + j))
    for i in range(32):
        a.ld(yd(H256 + i)); a.st(zp(RA256 + i))
    a.ld(imm(0)); a.st(zp(TCNT)); a.st(zp(WIDX)); a.st(zp(KIDX))
    a.label("c256_round")
    a.ld(zp(TCNT)); a.anda(imm(0x30))   # rounds 16 and up extend the message
    a.fit(8)
    a.branch("bne", "c256_sched"); a.nop()
    a.far("c256_plain")
    a.label("c256_sched")
    wfetch(XA, 0); wfetch(XB, 1); wfetch(XC, 9); wfetch(XD, 14)
    sigma(SG2, XB, [("rot", 7), ("rot", 18), ("shr", 3)], 4)
    add(zw(TA2, 4), zw(XA, 4), zw(SG2, 4))
    add(zw(TB2, 4), zw(TA2, 4), zw(XC, 4))
    sigma(SG2, XD, [("rot", 17), ("rot", 19), ("shr", 10)], 4)
    add(zw(WW2, 4), zw(TB2, 4), zw(SG2, 4))
    for j in range(4):
        a.ld(zp(WIDX)); a.adda(imm(WZ + j)); a.ld(AC, "X"); a.ld(zp(WW2 + j)); a.st(IX)
    a.far("c256_have")
    a.label("c256_plain")
    wfetch(WW2, 0)
    a.label("c256_have")
    a.page(PAGE_K256)
    for j in range(4):
        a.ld(zp(KIDX)); a.adda(imm(j)); a.ld(AC, "X"); a.ld(YX); a.st(zp(KW2 + j))
    sigma(SG2, E, [("rot", 6), ("rot", 11), ("rot", 25)], 4)
    add(zw(TA2, 4), zw(H, 4), zw(SG2, 4))
    for j in range(4):
        a.ld(zp(F + j)); a.xora(zp(G + j)); a.anda(zp(E + j)); a.xora(zp(G + j)); a.st(zp(CT2 + j))
    add(zw(TB2, 4), zw(TA2, 4), zw(CT2, 4))
    add(zw(TA2, 4), zw(TB2, 4), zw(KW2, 4))
    add(zw(TB2, 4), zw(TA2, 4), zw(WW2, 4))         # TB2 = t1
    sigma(SG2, A, [("rot", 2), ("rot", 13), ("rot", 22)], 4)
    for j in range(4):
        a.ld(zp(B + j)); a.xora(zp(C + j)); a.st(zp(S2_SUM))
        a.ld(zp(A + j)); a.xora(zp(B + j)); a.anda(zp(S2_SUM)); a.xora(zp(B + j)); a.st(zp(CT2 + j))
    add(zw(TA2, 4), zw(SG2, 4), zw(CT2, 4))         # TA2 = t2
    for dst, src in ((H, G), (G, F), (F, E)):       # the eight words move along one place
        for j in range(4): a.ld(zp(src + j)); a.st(zp(dst + j))
    add(zw(E, 4), zw(D, 4), zw(TB2, 4))
    for dst, src in ((D, C), (C, B), (B, A)):
        for j in range(4): a.ld(zp(src + j)); a.st(zp(dst + j))
    add(zw(A, 4), zw(TB2, 4), zw(TA2, 4))
    a.ld(zp(WIDX)); a.adda(imm(4)); a.anda(imm(63)); a.st(zp(WIDX))
    a.ld(zp(KIDX)); a.adda(imm(4)); a.st(zp(KIDX))
    a.ld(zp(TCNT)); a.adda(imm(1)); a.st(zp(TCNT))
    a.xora(imm(64))
    far_if_not_zero("c256_round")
    a.page(M256)
    for i in range(8):
        add(yw(H256 + 4 * i, 4), yw(H256 + 4 * i, 4), zw(RA256 + 4 * i, 4))
    ret("C2RET")

    # sha256: pad the message of S_LEN bytes to S_TOTAL (64 or 128), hash, leave the result at DG
    a.label("sha256")
    a.ld(v("S_LEN"), "X"); a.page(M256); a.ld(imm(0x80)); a.st(YX)
    setv("FPG", M256)
    a.ld(v("S_LEN")); a.adda(imm(1)); a.st(v("FFROM"))
    a.ld(zp(S_TOTAL)); a.suba(imm(2)); a.st(v("FEND"))
    setv("FVAL", 0)
    call("fill", "RET0")
    a.ld(zp(S_TOTAL)); a.suba(imm(2)); a.ld(AC, "X"); a.page(M256); a.ld(v("S_BH")); a.st(YX)
    a.ld(zp(S_TOTAL)); a.suba(imm(1)); a.ld(AC, "X"); a.ld(v("S_BL")); a.st(YX)
    for i in range(32):
        a.ld(yd(IV256 + i)); a.st(yd(H256 + i))
    call("c256", "C2RET")
    a.ld(zp(S_TOTAL)); a.xora(imm(64))
    a.fit(8)
    a.branch("bne", "s2_second"); a.nop()
    a.far("s2_out")
    a.label("s2_second")
    copy(M256, 64, M256, 0, 64)
    call("c256", "C2RET")
    a.label("s2_out")
    a.page(M256)
    for i in range(8):
        for j in range(4):
            a.ld(yd(H256 + 4 * i + 3 - j)); a.st(zp(DG + 4 * i + j))
    a.jump_via(R256H, R256L)

def sha256(length, total):
    setv("S_LEN", length); a.ld(imm(total)); a.st(zp(S_TOTAL))
    setv("S_BH", (length * 8) >> 8); setv("S_BL", (length * 8) & 0xFF)
    call("sha256", R256L, R256H)

# =============================================================================
# RIPEMD-160 of the 32 bytes at DG. Only the first 4 result bytes are kept (FPOUT).
# =============================================================================
RR, LS, FT, RTA, RTB, XW, RKW, RU = 0x01, 0x15, 0x29, 0x2D, 0x31, 0x35, 0x39, 0x3D
RMD = {n: 0x41 + i for i, n in enumerate(
    "STEP PGL PGR QF FS LINEPG QOFF KOFF FOFF SUM RETL RETH RND LRETL LRETH KX".split())}
RBLK = DG                               # the 64-byte block starts with the 32 input bytes
RT_X, RT_PGL, RT_PGR = 0x00, 0x50, 0xA0  # in RT_L / RT_R: per step, message offset and shift tables
RT_QL, RT_QR, RT_KL, RT_KR, RT_FL, RT_FR, RT_IV = 0x00, 0x50, 0xA0, 0xB4, 0xC8, 0xCD, 0xD2   # in RT_M

def init_ripemd_tables():
    for page, rt, st_ in ((RT_L, k._RL, k._SL), (RT_R, k._RR, k._SR)):
        flat = [(rt[r][i], st_[r][i]) for r in range(5) for i in range(16)]
        poke(page, RT_X, [4 * r for r, s in flat])
        poke(page, RT_PGL, [PAGE_SHL + s % 8 for r, s in flat])
        poke(page, RT_PGR, [PAGE_SHR + 8 - s % 8 for r, s in flat])
    poke(RT_M, RT_QL, [s // 8 for r in range(5) for s in k._SL[r]])
    poke(RT_M, RT_QR, [s // 8 for r in range(5) for s in k._SR[r]])
    poke(RT_M, RT_KL, b"".join(x.to_bytes(4, "little") for x in k._KL))
    poke(RT_M, RT_KR, b"".join(x.to_bytes(4, "little") for x in k._KR))
    poke(RT_M, RT_FL, [0, 1, 2, 3, 4]); poke(RT_M, RT_FR, [4, 3, 2, 1, 0])
    poke(RT_M, RT_IV, b"".join(x.to_bytes(4, "little") for x in
                               (0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0)))

def routines_ripemd():
    SUM[0] = RMD["SUM"]
    r = lambda n: zp(RMD[n])
    A, B, C, D, E = (RR + 4 * i for i in range(5))
    a.label("rmd")
    a.ld(imm(0x80)); a.st(zp(RBLK + 32))
    a.ld(imm(0))
    for i in range(33, 64): a.st(zp(RBLK + i))
    a.ld(imm(1)); a.st(zp(RBLK + 57))   # length 256 bits, low byte first
    for line, (page, qoff, koff, foff) in enumerate(((RT_L, RT_QL, RT_KL, RT_FL), (RT_R, RT_QR, RT_KR, RT_FR))):
        a.page(RT_M)
        for i in range(20):
            a.ld(yd(RT_IV + i)); a.st(zp(RR + i))
        for name, val in (("LINEPG", page), ("QOFF", qoff), ("KOFF", koff), ("FOFF", foff), ("STEP", 0)):
            a.ld(imm(val)); a.st(r(name))
        call("rmd_line", RMD["LRETL"], RMD["LRETH"])
        if line == 0:
            for i in range(20):
                a.ld(zp(RR + i)); a.st(zp(LS + i))
    a.page(RT_M)                        # first result word = IV1 + C(left) + D(right)
    add(zw(RTA, 4), yw(RT_IV + 4, 4), zw(LS + 8, 4))
    add(zw(FPOUT, 4), zw(RTA, 4), zw(D, 4))
    a.jump_via(RMD["RETH"], RMD["RETL"])

    a.label("rmd_line")                 # 80 steps down one line
    a.label("rl_step")
    a.ld(r("STEP"), "X"); a.ld(r("LINEPG"), "Y")
    a.ld(YX); a.adda(imm(RBLK)); a.st(r("KX"))
    for j in range(4):                  # the message word this step uses
        a.ld(r("KX")); a.adda(imm(j)); a.ld(AC, "X"); a.ld(IX); a.st(zp(XW + j))
    a.ld(r("STEP")); a.adda(imm(RT_PGL)); a.ld(AC, "X"); a.ld(YX); a.st(r("PGL"))
    a.ld(r("STEP")); a.adda(imm(RT_PGR)); a.ld(AC, "X"); a.ld(YX); a.st(r("PGR"))
    a.page(RT_M)
    a.ld(r("STEP")); a.adda(r("QOFF")); a.ld(AC, "X"); a.ld(YX); a.st(r("QF"))
    a.ld(r("STEP"), "X"); a.page(PAGE_SHR + 4); a.ld(YX); a.st(r("RND"))     # round = step / 16
    a.ld(r("RND"), "X"); a.page(PAGE_SHL + 2); a.ld(YX); a.adda(r("KOFF")); a.st(r("KX"))
    a.page(RT_M)
    for j in range(4):                  # the round constant
        a.ld(r("KX")); a.adda(imm(j)); a.ld(AC, "X"); a.ld(YX); a.st(zp(RKW + j))
    a.ld(r("RND")); a.adda(r("FOFF")); a.ld(AC, "X"); a.ld(YX); a.st(r("FS"))
    for n in range(4):                  # choose the mixing function
        a.ld(r("FS")); a.xora(imm(n))
        a.fit(8)
        a.branch("bne", f"rl_nf{n}"); a.nop()
        a.far(f"rl_f{n}")
        a.label(f"rl_nf{n}")
    a.far("rl_f4")
    mixes = [lambda j: (a.ld(zp(B + j)), a.xora(zp(C + j)), a.xora(zp(D + j))),                      # x^y^z
             lambda j: (a.ld(zp(C + j)), a.xora(zp(D + j)), a.anda(zp(B + j)), a.xora(zp(D + j))),   # (x&y)|(~x&z)
             lambda j: (a.ld(zp(C + j)), a.xora(imm(0xFF)), a.ora(zp(B + j)), a.xora(zp(D + j))),    # (x|~y)^z
             lambda j: (a.ld(zp(B + j)), a.xora(zp(C + j)), a.anda(zp(D + j)), a.xora(zp(C + j))),   # (x&z)|(y&~z)
             lambda j: (a.ld(zp(D + j)), a.xora(imm(0xFF)), a.ora(zp(C + j)), a.xora(zp(B + j)))]    # x^(y|~z)
    for n, mix in enumerate(mixes):
        a.label(f"rl_f{n}")
        for j in range(4):
            mix(j); a.st(zp(FT + j))
        a.far("rl_join")
    a.label("rl_join")
    add(zw(RTA, 4), zw(A, 4), zw(FT, 4))
    add(zw(RTB, 4), zw(RTA, 4), zw(XW, 4))
    add(zw(RTA, 4), zw(RTB, 4), zw(RKW, 4))
    for j in range(4):                  # rotate left by 0-7 bits using this step's two tables
        a.ld(zp(RTA + j), "X"); a.ld(r("PGL"), "Y"); a.ld(YX)
        a.ld(zp(RTA + (j - 1) % 4), "X"); a.ld(r("PGR"), "Y"); a.ora(YX)
        a.st(zp(RU + j))
    a.ld(r("QF"))                       # and by one whole byte more if the shift is 8 or over
    a.fit(16)
    a.branch("beq", "rl_noq"); a.nop()
    a.ld(zp(RU + 3)); a.st(r("SUM"))
    for j in (3, 2, 1):
        a.ld(zp(RU + j - 1)); a.st(zp(RU + j))
    a.ld(r("SUM")); a.st(zp(RU))
    a.label("rl_noq")
    add(zw(RTB, 4), zw(RU, 4), zw(E, 4))
    for j in range(4): a.ld(zp(E + j)); a.st(zp(A + j))              # a = e
    for j in range(4): a.ld(zp(D + j)); a.st(zp(E + j))              # e = d
    for j in range(4):                                               # d = c rotated left 10
        a.ld(zp(C + (j - 1) % 4), "X"); a.page(PAGE_SHL + 2); a.ld(YX)
        a.ld(zp(C + (j - 2) % 4), "X"); a.page(PAGE_SHR + 6); a.ora(YX)
        a.st(zp(D + j))
    for j in range(4): a.ld(zp(B + j)); a.st(zp(C + j))              # c = b
    for j in range(4): a.ld(zp(RTB + j)); a.st(zp(B + j))            # b = the new value
    a.ld(r("STEP")); a.adda(imm(1)); a.st(r("STEP"))
    a.xora(imm(80))
    far_if_not_zero("rl_step")
    a.jump_via(RMD["LRETH"], RMD["LRETL"])

# =============================================================================
# glue
# =============================================================================
def routines_glue():
    SUM[0] = Z["SUMTMP"]
    # hmac_key: the two starting states for a keyed hash. Key: HK_LEN bytes at (HK_SP, HK_SO).
    a.label("hmac_key")
    for pad, dst in ((0x36, IPAD), (0x5C, OPAD)):
        fill(SIO, BLK, BLK + 128, pad)
        setv("HKS", v("HK_SO")); setv("HKD", BLK); setv("HKC", v("HK_LEN"))
        a.fit(24)
        top = f"t{a.pc}"
        a.label(top)
        a.ld(v("HKS"), "X"); a.ld(v("HK_SP"), "Y"); a.ld(YX); a.xora(imm(pad))
        a.ld(v("HKD"), "X"); a.ld(imm(SIO), "Y"); a.st(YX)
        a.ld(v("HKS")); a.adda(imm(1)); a.st(v("HKS"))
        a.ld(v("HKD")); a.adda(imm(1)); a.st(v("HKD"))
        a.ld(v("HKC")); a.suba(imm(1)); a.st(v("HKC"))
        a.branch("bne", top); a.nop()
        copy(D1, IV512, SIO, H5, 64)
        compress512()
        copy(SIO, H5, D1, dst, 64)
    ret("GRET")

    # hmac_tail: the block at SIO.BLK is a padded message. Result: 64 bytes at SIO.DIG.
    a.label("hmac_tail")
    copy(D1, IPAD, SIO, H5, 64)
    compress512()
    call("h2dig", "HRET"); call("dig2blk", "HRET")
    copy(D1, OPAD, SIO, H5, 64)
    compress512()
    call("h2dig", "HRET")
    ret("GRET")

    # pbkdf2: the 2,048 rounds. Text at D0.TEXT, TLEN bytes. Seed: 64 bytes at D1.TACC.
    a.label("pbkdf2")
    setv("HK_SP", D0); setv("HK_SO", TEXT); setv("HK_LEN", v("TLEN"))
    call("hmac_key", "GRET")
    copy(D0, SALT, SIO, BLK, 12)        # "mnemonic", 0, 0, 0, 1
    a.page(SIO); a.ld(imm(0x80)); a.st(yd(BLK + 12))
    fill(SIO, BLK + 13, BLK + 126)
    a.page(SIO); a.ld(imm(0x04)); a.st(yd(BLK + 126)); a.ld(imm(0x60)); a.st(yd(BLK + 127))   # 140 bytes
    call("hmac_tail", "GRET")
    copy(SIO, DIG, D1, TACC, 64)
    setv("PB_LO", 2047 & 0xFF); setv("PB_HI", 2047 >> 8)
    a.label("pb_loop")
    call("dig2blk", "HRET")
    call("hmac_tail", "GRET")
    setv("XI", 0)                       # running XOR of every round's result
    a.fit(32)
    a.label("pb_xor")
    a.ld(v("XI")); a.adda(imm(DIG)); a.ld(AC, "X"); a.ld(imm(SIO), "Y"); a.ld(YX); a.st(v("BITV"))
    a.ld(v("XI")); a.adda(imm(TACC)); a.ld(AC, "X"); a.ld(imm(D1), "Y"); a.ld(YX); a.xora(v("BITV")); a.st(YX)
    a.ld(v("XI")); a.adda(imm(1)); a.st(v("XI")); a.xora(imm(64))
    a.branch("bne", "pb_xor"); a.nop()
    a.fit(16)
    a.ld(v("PB_LO"))
    a.branch("bne", "pb_nb"); a.nop()
    a.ld(v("PB_HI")); a.suba(imm(1)); a.st(v("PB_HI"))
    a.label("pb_nb")
    a.ld(v("PB_LO")); a.suba(imm(1)); a.st(v("PB_LO"))
    a.ora(v("PB_HI"))
    far_if_not_zero("pb_loop")
    ret("G2RET")

    # modn: KEY = (KEY + IL) mod the curve order, all in page D2
    a.label("modn")
    a.page(D2)
    add(yw(SA, 32), yw(KEY, 32), yw(IL, 32), cout=True)
    a.st(yd(SA + 32))
    add(yw(SB, 33), yw(SA, 33), yw(NOTN, 33), cin=1, cout=True)
    a.fit(6)
    a.branch("beq", "modn_sel")         # carry 0: the sum was below the order, keep it
    a.ld(imm(SA))
    a.ld(imm(SB))
    a.label("modn_sel")
    a.st(v("HKS"))
    copy(D2, v("HKS"), D2, KEY, 32)
    ret("GRET")

    # fingerprint: first 4 bytes of RIPEMD-160(SHA-256(public key of KEY)) -> FPOUT
    a.label("fingerprint")
    copy(D2, KEY, CIO, K_OFF, 32)
    call("pubkey", "PKRET")
    copy(CIO, OUT_OFF, M256, 0, 33)
    sha256(33, 64)
    call("rmd", RMD["RETL"], RMD["RETH"])
    ret("G2RET")

    # putbit: append one bit (BITV zero / not zero) to the byte stream at (page OPG, offset OPTR)
    a.label("putbit")
    a.ld(v("ACCB")); a.adda(AC); a.st(v("ACCB"))
    a.ld(v("BITV"))
    a.fit(8)
    a.branch("beq", "pb_zero"); a.nop()
    a.ld(v("ACCB")); a.adda(imm(1)); a.st(v("ACCB"))
    a.label("pb_zero")
    a.ld(v("BCNT")); a.adda(imm(1)); a.st(v("BCNT")); a.xora(imm(8))
    a.fit(16)
    a.branch("bne", "pb_ret"); a.nop()
    a.ld(v("OPTR"), "X"); a.ld(v("OPG"), "Y"); a.ld(v("ACCB")); a.st(YX)
    a.ld(v("OPTR")); a.adda(imm(1)); a.st(v("OPTR"))
    a.ld(imm(0)); a.st(v("BCNT"))
    a.label("pb_ret")
    ret("PBRET")

    # nextch: next character of the word list -> AC and BITV; moves the pointer on
    a.label("nextch")
    a.ld(v("WOF"), "X"); a.ld(v("WPG"), "Y"); a.ld(YX); a.st(v("BITV"))
    a.ld(v("WOF")); a.adda(imm(1)); a.st(v("WOF"))
    a.fit(8)
    a.branch("bne", "nc_same"); a.nop()
    a.ld(v("WPG")); a.adda(imm(1)); a.st(v("WPG"))
    a.label("nc_same")
    a.ld(v("BITV"))
    ret("PBRET")


# =============================================================================
# text and QR
# =============================================================================
def qr_template(mask=0):
    """The fixed furniture of a version-6 QR code, as keycalc.qr_rows lays it out.
    Each square: bit 0 = dark, bit 1 = fixed (not available for data)."""
    n = 41
    m = [[0] * n for _ in range(n)]
    def put(x, y, val): m[y][x] = 2 | int(bool(val))
    for i in range(n):
        put(6, i, i % 2 == 0); put(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                if 0 <= cx + dx < n and 0 <= cy + dy < n:
                    put(cx + dx, cy + dy, max(abs(dx), abs(dy)) not in (2, 4))
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            put(34 + dx, 34 + dy, max(abs(dx), abs(dy)) != 1)
    val = (1 << 3 | mask) << 10
    rem = val
    for i in range(14, 9, -1):
        if rem >> i & 1: rem ^= 0x537 << (i - 10)
    val = (val | rem) ^ 0x5412
    bit = lambda i: val >> i & 1
    for i in range(6): put(8, i, bit(i))
    put(8, 7, bit(6)); put(8, 8, bit(7)); put(7, 8, bit(8))
    for i in range(9, 15): put(14 - i, 8, bit(i))
    for i in range(8): put(n - 1 - i, 8, bit(i))
    for i in range(8, 15): put(8, n - 15 + i, bit(i))
    put(8, n - 8, 1)
    return m

def rs_generator(n=18):
    """Coefficients of the check-byte polynomial, as in keycalc._rs_remainder."""
    gen = [1]
    for i in range(n):
        gen = [(gen[j] if j < len(gen) else 0) ^ (k._EXP[k._LOG[gen[j - 1]] + i] if j and gen[j - 1] else 0)
               for j in range(len(gen) + 1)]
    return gen

def init_text_qr():
    """Small tables that last the whole run."""
    poke(CHARS, ALPHA, b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
    poke(CHARS, HEXC, b"0123456789abcdef")
    poke(DESCPG, 0, b"["); poke(DESCPG, 9, b"/84h/0h/0h]")
    # divide-by-58 tables: entry (remainder * 16 + nibble) -> quotient, and -> new remainder
    setv("QP", 0); a.st(v("QO")); a.st(v("QQ")); a.st(v("QRM"))
    a.fit(64)
    a.label("q58")
    a.ld(v("QP")); a.adda(imm(PAGE_Q58)); a.ld(AC, "Y"); a.ld(v("QO"), "X"); a.ld(v("QQ")); a.st(YX)
    a.ld(v("QP")); a.adda(imm(PAGE_R58)); a.ld(AC, "Y"); a.ld(v("QRM")); a.st(YX)
    a.ld(v("QRM")); a.adda(imm(1)); a.st(v("QRM")); a.xora(imm(58))
    a.branch("bne", "q58_same"); a.nop()
    a.ld(imm(0)); a.st(v("QRM")); a.ld(v("QQ")); a.adda(imm(1)); a.st(v("QQ"))
    a.label("q58_same")
    a.ld(v("QO")); a.adda(imm(1)); a.st(v("QO"))
    a.branch("bne", "q58"); a.nop()
    a.ld(v("QP")); a.adda(imm(1)); a.st(v("QP")); a.xora(imm(4))
    a.branch("bne", "q58"); a.nop()
    # "times two" in the QR code's byte arithmetic: shift left, and fold back if the top bit fell off
    def xtime():
        a.ld(v("CNT"), "X"); a.page(PAGE_SHL + 1); a.ld(YX); a.st(v("TMPB"))
        a.ld(v("CNT"))
        a.branch("bge", "xt_low"); a.nop()
        a.ld(v("TMPB")); a.xora(imm(0x1D)); a.st(v("TMPB"))
        a.label("xt_low")
        a.ld(v("CNT"), "X"); a.page(XTPG); a.ld(v("TMPB")); a.st(YX)
    table_loop(xtime)

def interleave(src_a, src_b, count, dst):
    """STREAM[dst + 2i] = QDPG[src_a + i], STREAM[dst + 2i + 1] = QDPG[src_b + i]"""
    setv("SI", 0); setv("DI", dst)
    a.fit(48)
    top = f"t{a.pc}"
    a.label(top)
    for src in (src_a, src_b):
        a.ld(v("SI")); a.adda(imm(src)); a.ld(AC, "X"); a.ld(imm(QDPG), "Y"); a.ld(YX); a.st(v("TMPB"))
        a.ld(v("DI"), "X"); a.ld(imm(STREAMPG), "Y"); a.ld(v("TMPB")); a.st(YX)
        a.ld(v("DI")); a.adda(imm(1)); a.st(v("DI"))
    a.ld(v("SI")); a.adda(imm(1)); a.st(v("SI")); a.xora(imm(count))
    a.branch("bne", top); a.nop()

def main_mkqr():
    """mkqr: the key record at IOP.BODY -> zpub text -> descriptor -> QR code in MATRIX."""
    a.label("mkqr")
    # 1. the 82-byte record: version, the 74 bytes from calc, 4 checksum bytes (SHA-256 twice)
    a.page(B58PG)
    for i, b in enumerate((0x04, 0xB2, 0x47, 0x46)):
        a.ld(imm(b)); a.st(yd(PAY + i))
    copy(IOP, BODY, B58PG, PAY + 4, 74)
    copy(B58PG, PAY, M256, 0, 78)
    sha256(78, 128)
    copy(0, DG, M256, 0, 32)
    sha256(32, 64)
    a.page(B58PG)
    for j in range(4):
        a.ld(zp(DG + j)); a.st(yd(PAY + 78 + j))
    # 2. base 58: divide the whole record by 58, 111 times; each remainder is one character
    setv("B58N", 110)
    a.label("b58_digit")
    setv("B58REM", 0); setv("B58I", 0)
    a.fit(110)
    a.label("b58_byte")
    a.ld(v("B58I"), "X"); a.ld(imm(B58PG), "Y"); a.ld(YX); a.st(v("BYTE"))
    for half in (0, 1):                 # high nibble, then low nibble
        a.ld(v("B58REM"), "X"); a.page(PAGE_SHR + 4); a.ld(YX); a.st(v("QPG_"))
        a.page(PAGE_SHL + 4); a.ld(YX); a.st(v("OFFT"))
        if half == 0:
            a.ld(v("BYTE"), "X"); a.page(PAGE_SHR + 4); a.ld(YX)
        else:
            a.ld(v("BYTE")); a.anda(imm(15))
        a.ora(v("OFFT")); a.ld(AC, "X")
        a.ld(v("QPG_")); a.adda(imm(PAGE_Q58)); a.ld(AC, "Y"); a.ld(YX); a.st(v("Q2" if half else "Q1"))
        a.ld(v("QPG_")); a.adda(imm(PAGE_R58)); a.ld(AC, "Y"); a.ld(YX); a.st(v("B58REM"))
    a.ld(v("Q1"), "X"); a.page(PAGE_SHL + 4); a.ld(YX); a.ora(v("Q2")); a.st(v("TMPB"))
    a.ld(v("B58I"), "X"); a.ld(imm(B58PG), "Y"); a.ld(v("TMPB")); a.st(YX)
    a.ld(v("B58I")); a.adda(imm(1)); a.st(v("B58I")); a.xora(imm(82))
    a.branch("bne", "b58_byte"); a.nop()
    a.ld(v("B58REM"), "X"); a.page(CHARS); a.ld(YX); a.st(v("TMPB"))
    a.ld(v("B58N")); a.adda(imm(ZTXT)); a.ld(AC, "X"); a.page(B58PG); a.ld(v("TMPB")); a.st(YX)
    a.ld(v("B58N")); a.suba(imm(1)); a.st(v("B58N")); a.xora(imm(0xFF))
    far_if_not_zero("b58_digit")
    # 3. the descriptor: [fingerprint/84h/0h/0h]zpub...   (131 characters)
    for j in range(4):
        a.page(IOP); a.ld(yd(OUT_FP + j)); a.st(v("BYTE"))
        a.ld(v("BYTE"), "X"); a.page(PAGE_SHR + 4); a.ld(YX); a.adda(imm(HEXC)); a.ld(AC, "X")
        a.page(CHARS); a.ld(YX); a.page(DESCPG); a.st(yd(1 + 2 * j))
        a.ld(v("BYTE")); a.anda(imm(15)); a.adda(imm(HEXC)); a.ld(AC, "X")
        a.page(CHARS); a.ld(YX); a.page(DESCPG); a.st(yd(2 + 2 * j))
    copy(B58PG, ZTXT, DESCPG, 20, 111)
    # 4. QR data bytes: 4 bits of type, 8 bits of length, the text, an end mark, padding.
    #    Everything is shifted by half a byte, so each data byte joins two neighbouring characters.
    a.page(QDPG); a.ld(imm(0x48)); a.st(yd(QDATA))
    setv("PREV", 131); setv("QI", 0)
    a.fit(48)
    a.label("qd")
    a.ld(v("QI"), "X"); a.ld(imm(DESCPG), "Y"); a.ld(YX); a.st(v("BYTE"))
    a.ld(v("PREV"), "X"); a.page(PAGE_SHL + 4); a.ld(YX); a.st(v("OFFT"))
    a.ld(v("BYTE"), "X"); a.page(PAGE_SHR + 4); a.ld(YX); a.ora(v("OFFT")); a.st(v("TMPB"))
    a.ld(v("QI")); a.adda(imm(QDATA + 1)); a.ld(AC, "X"); a.page(QDPG); a.ld(v("TMPB")); a.st(YX)
    a.ld(v("BYTE")); a.st(v("PREV"))
    a.ld(v("QI")); a.adda(imm(1)); a.st(v("QI")); a.xora(imm(131))
    a.branch("bne", "qd"); a.nop()
    a.ld(v("PREV"), "X"); a.page(PAGE_SHL + 4); a.ld(YX); a.page(QDPG); a.st(yd(QDATA + 132))
    a.ld(imm(0xEC)); a.st(yd(QDATA + 133)); a.st(yd(QDATA + 135))
    a.ld(imm(0x11)); a.st(yd(QDATA + 134))
    # 5. check bytes. First a times-table for each of the 18 coefficients, then two blocks of 68.
    for j, g in enumerate(rs_generator()[1:]):
        setv("GPG", PAGE_MULG + j); setv("GV", g)
        call("mulg", "MRET")
    for blk in (0, 1):
        a.ld(imm(0))
        for j in range(19): a.st(zp(RS + j))
        setv("RSI", QDATA + 68 * blk); setv("RSC", 68)
        top = f"rs{blk}"
        a.label(top)
        a.ld(v("RSI"), "X"); a.page(QDPG); a.ld(YX); a.xora(zp(RS)); a.ld(AC, "X")
        for j in range(18):
            a.ld(zp(RS + j + 1)); a.page(PAGE_MULG + j); a.xora(YX); a.st(zp(RS + j))
        a.ld(v("RSI")); a.adda(imm(1)); a.st(v("RSI"))
        a.ld(v("RSC")); a.suba(imm(1)); a.st(v("RSC"))
        far_if_not_zero(top)
        a.page(QDPG)
        for j in range(18):
            a.ld(zp(RS + j)); a.st(yd((ECC0, ECC1)[blk] + j))
    # 6. the bytes in the order they go into the code: the two blocks taken alternately
    fill(STREAMPG, 172, 180)
    interleave(QDATA, QDATA + 68, 68, 0)
    interleave(ECC0, ECC1, 18, 136)
    # 7. the fixed furniture (corner markers, timing lines, format bits for mask 0)
    for y, row in enumerate(qr_template(0)):
        poke(MATRIX + y, 0, row)
    # 8. the data bits, zig-zagging in two-wide columns from the right; mask 0 flips
    #    every square where column + row is even
    setv("QRIGHT", 40); setv("SPTR", 0); setv("SMASK", 0x80)
    a.label("q_col")
    a.ld(v("QRIGHT")); a.adda(imm(1)); a.anda(imm(2)); a.st(v("QUP"))    # 0 = this column runs upward
    setv("QVERT", 0)
    a.label("q_vert")
    a.ld(v("QUP"))
    a.fit(8)
    a.branch("bne", "q_down")
    a.ld(v("QVERT"))
    a.ld(imm(40)); a.suba(v("QVERT"))
    a.label("q_down")
    a.st(v("QY"))
    for j in (0, 1):
        a.ld(v("QRIGHT"))
        if j: a.suba(imm(1))
        a.st(v("QX"))
        call("qplace", "QRET")
    a.ld(v("QVERT")); a.adda(imm(1)); a.st(v("QVERT")); a.xora(imm(41))
    far_if_not_zero("q_vert")
    a.ld(v("QRIGHT")); a.suba(imm(2)); a.st(v("QRIGHT")); a.xora(imm(6))
    a.fit(8)
    a.branch("bne", "q_not6"); a.nop()
    a.ld(imm(5)); a.st(v("QRIGHT"))     # column 6 is a timing line: step over it
    a.label("q_not6")
    a.ld(v("QRIGHT"))
    a.fit(8)
    a.branch("blt", "q_done"); a.nop()
    a.far("q_col")
    a.label("q_done")
    ret("QRRET")

def routines_text_qr():
    # mulg: table at page GPG, entry f = GV * f in the QR code's byte arithmetic
    a.label("mulg")
    a.ld(v("GPG"), "Y"); a.ld(imm(0), "X"); a.ld(imm(0)); a.st(YX)
    a.ld(imm(1), "X"); a.ld(v("GV")); a.st(YX)
    setv("CNT2", 1)
    a.fit(48)
    a.label("mg")
    a.ld(v("CNT2"), "X"); a.ld(v("GPG"), "Y"); a.ld(YX); a.ld(AC, "X")
    a.ld(imm(XTPG), "Y"); a.ld(YX); a.st(v("TMPB"))                  # twice entry f
    a.ld(v("CNT2")); a.adda(AC); a.ld(AC, "X"); a.ld(v("GPG"), "Y"); a.ld(v("TMPB")); a.st(YX)
    a.xora(v("GV")); a.st(v("TMPB"))                                 # ... plus one more GV
    a.ld(v("CNT2")); a.adda(AC); a.adda(imm(1)); a.ld(AC, "X"); a.ld(v("TMPB")); a.st(YX)
    a.ld(v("CNT2")); a.adda(imm(1)); a.st(v("CNT2")); a.xora(imm(128))
    a.branch("bne", "mg"); a.nop()
    ret("MRET")

    # qplace: if square (QX, QY) is free, put the next data bit there (masked)
    a.label("qplace")
    a.ld(v("QY")); a.adda(imm(MATRIX)); a.ld(AC, "Y"); a.ld(v("QX"), "X"); a.ld(YX); a.anda(imm(2))
    a.fit(8)
    a.branch("beq", "qp_free"); a.nop()
    ret("QRET")
    a.label("qp_free")
    a.ld(v("SPTR"), "X"); a.page(STREAMPG); a.ld(YX); a.anda(v("SMASK")); a.st(v("QBIT"))
    a.ld(v("SMASK"), "X"); a.page(PAGE_SHR + 1); a.ld(YX); a.st(v("SMASK"))
    a.fit(8)
    a.branch("bne", "qp_same"); a.nop()
    a.ld(imm(0x80)); a.st(v("SMASK")); a.ld(v("SPTR")); a.adda(imm(1)); a.st(v("SPTR"))
    a.label("qp_same")
    a.ld(v("QX")); a.adda(v("QY")); a.adda(imm(1)); a.anda(imm(1)); a.st(v("TMPB"))    # 1 where the mask flips
    a.ld(v("QBIT"))
    a.fit(8)
    a.branch("beq", "qp_zero"); a.nop()
    a.ld(v("TMPB")); a.xora(imm(1)); a.st(v("TMPB"))
    a.label("qp_zero")
    a.ld(v("QY")); a.adda(imm(MATRIX)); a.ld(AC, "Y"); a.ld(v("QX"), "X"); a.ld(v("TMPB")); a.st(YX)
    ret("QRET")

# =============================================================================
# the switch and light module on the game controller port
# =============================================================================
# Two lines out: PULSE (OUT bit 6) and LATCH (OUT bit 7). One line in: DATA.
#   lights:   each PULSE rising edge shifts the level of LATCH into the light chain;
#             a LATCH rising edge puts the chain on the lights
#   switches: LATCH low loads them; with LATCH high each PULSE brings in one bit
# The light frame is 56 bits: 41 row lights, 7 unused, then a status byte
# (top two bits: 0 entering words, 1 busy, 2 showing the 12th word, 3 showing a QR row;
#  low six bits: words entered so far, or the row number).
P_LO, P_HI = 0x00, 0x40
L_LO, L_HI = 0x00, 0x80
MODE_ENTRY, MODE_BUSY, MODE_WORD, MODE_ROW = 0x00, 0x40, 0x80, 0xC0
BTN_STORE, BTN_NEXT = 0x80, 0x40        # in the second input byte; its low 3 bits are the top of the word number

def routines_module():
    # io_show: send the 7 frame bytes to the lights
    a.label("io_show")
    setv("IOI", 0)
    a.label("is_byte")
    a.ld(v("IOI")); a.adda(imm(FRAME)); a.ld(AC, "X"); a.page(CHARS); a.ld(YX); a.st(v("IOB"))
    setv("IOM", 0x80)
    a.fit(40)
    a.label("is_bit")
    a.ld(v("IOB")); a.anda(v("IOM"))
    a.branch("beq", "is_zero"); a.nop()
    a.ld(imm(L_HI | P_LO), "OUT"); a.ld(imm(L_HI | P_HI), "OUT")
    a.branch("bra", "is_next"); a.nop()
    a.label("is_zero")
    a.ld(imm(L_LO | P_LO), "OUT"); a.ld(imm(L_LO | P_HI), "OUT")
    a.label("is_next")
    a.ld(v("IOM"), "X"); a.page(PAGE_SHR + 1); a.ld(YX); a.st(v("IOM"))
    a.branch("bne", "is_bit"); a.nop()
    a.ld(v("IOI")); a.adda(imm(1)); a.st(v("IOI")); a.xora(imm(7))
    far_if_not_zero("is_byte")
    a.ld(imm(L_LO | P_LO), "OUT"); a.ld(imm(L_HI | P_LO), "OUT")    # LATCH rises: lights update
    ret("IORET")

    # io_read: the 16 inputs -> IOB1, IOB2 (1 = switch on / button down)
    a.label("io_read")
    a.ld(imm(L_LO | P_LO), "OUT"); a.ld(imm(L_HI | P_LO), "OUT")    # load, then shift mode
    # The Gigatron's input register (U39, 74HC595) shows its value one pulse
    # late, so one extra pulse goes first: 9 pulses for byte 1, 17 for byte 2.
    a.ld(imm(L_HI | P_HI), "OUT"); a.ld(imm(L_HI | P_LO), "OUT")
    for cell in ("IOB1", "IOB2"):
        for _ in range(8):
            a.ld(imm(L_HI | P_HI), "OUT"); a.ld(imm(L_HI | P_LO), "OUT")
        a.ld(IN); a.xora(imm(0xFF)); a.st(v(cell))
    ret("IORET")

    # delay: DLY2 * about 0.2 ms
    a.label("delay")
    a.fit(16)
    a.label("dl")
    a.ld(v("DLY1")); a.suba(imm(1)); a.st(v("DLY1"))
    a.branch("bne", "dl"); a.nop()
    a.ld(v("DLY2")); a.suba(imm(1)); a.st(v("DLY2"))
    a.branch("bne", "dl"); a.nop()
    ret("DRET")

    def frame_start():
        setv("OPG", CHARS); setv("OPTR", FRAME); setv("ACCB", 0); setv("BCNT", 0)
    def bit_from(cell, mask):
        a.ld(v(cell)); a.anda(imm(mask)); a.st(v("BITV"))
        call("putbit", "PBRET")
    # frame_word: an 11-bit number (WHI, WLO) on the first 11 lights
    a.label("frame_word")
    frame_start()
    for mask in (4, 2, 1): bit_from("WHI", mask)
    for mask in (128, 64, 32, 16, 8, 4, 2, 1): bit_from("WLO", mask)
    setv("ZCNT", 37)
    a.far("frame_pad")
    # frame_row: row ROWN of the QR code on the 41 lights
    a.label("frame_row")
    frame_start()
    setv("PKX", 0)
    a.label("fr_x")
    a.ld(v("ROWN")); a.adda(imm(MATRIX)); a.ld(AC, "Y"); a.ld(v("PKX"), "X"); a.ld(YX); a.anda(imm(1)); a.st(v("BITV"))
    call("putbit", "PBRET")
    a.ld(v("PKX")); a.adda(imm(1)); a.st(v("PKX")); a.xora(imm(41))
    far_if_not_zero("fr_x")
    setv("ZCNT", 7)
    a.label("frame_pad")                # ZCNT dark lights, then the status byte
    setv("BITV", 0)
    call("putbit", "PBRET")
    a.ld(v("ZCNT")); a.suba(imm(1)); a.st(v("ZCNT"))
    far_if_not_zero("frame_pad")
    a.page(CHARS); a.ld(v("STAT")); a.st(yd(FRAME + 6))
    ret("ZRET")

    # poll: read the inputs, refresh the lights (reading disturbs the light chain), pause.
    # With ECHO set, the lights follow the switches.
    a.label("poll")
    call("io_read", "IORET")
    a.ld(v("ECHO"))
    a.fit(8)
    a.branch("bne", "poll_echo"); a.nop()
    a.far("poll_show")
    a.label("poll_echo")
    a.ld(v("IOB1")); a.st(v("WLO")); a.ld(v("IOB2")); a.anda(imm(7)); a.st(v("WHI"))
    call("frame_word", "ZRET")
    a.label("poll_show")
    call("io_show", "IORET")
    setv("DLY2", 120)
    call("delay", "DRET")
    ret("PRET")

    # wait_btn: until (second input byte AND BMASK) equals BWANT on two polls running
    a.label("wait_btn")
    setv("BCNT2", 0)
    a.label("wb")
    call("poll", "PRET")
    a.ld(v("IOB2")); a.anda(v("BMASK")); a.xora(v("BWANT"))
    a.fit(12)
    a.branch("beq", "wb_hit"); a.nop()
    setv("BCNT2", 0)
    a.far("wb")
    a.label("wb_hit")
    a.ld(v("BCNT2")); a.adda(imm(1)); a.st(v("BCNT2")); a.xora(imm(2))
    far_if_not_zero("wb")
    ret("UIRET")

def press_and_release(button):
    setv("BMASK", button); setv("BWANT", button); call("wait_btn", "UIRET")
    setv("BWANT", 0); call("wait_btn", "UIRET")

def main_ui():
    """ui: the whole session. One run per power-up; reset to start again."""
    a.label("ui")
    setv("WLO", 0); setv("WHI", 0); setv("STAT", MODE_ENTRY)
    call("frame_word", "ZRET"); call("io_show", "IORET")
    setv("CNTW", 0)
    # eleven words, then the seven coin-flip bits (on the seven right-hand switches); STORE after each
    a.label("ui_entry")
    setv("ECHO", 1); setv("STAT", v("CNTW"))
    setv("BMASK", BTN_STORE); setv("BWANT", BTN_STORE); call("wait_btn", "UIRET")
    a.ld(v("CNTW")); a.xora(imm(11))
    a.fit(8)
    a.branch("bne", "ui_isword"); a.nop()
    a.far("ui_isbits")
    a.label("ui_isword")
    a.ld(v("CNTW")); a.adda(AC); a.adda(imm(IDX)); a.ld(AC, "X"); a.page(IOP); a.ld(v("IOB1")); a.st(YX)
    a.ld(v("CNTW")); a.adda(AC); a.adda(imm(IDX + 1)); a.ld(AC, "X"); a.ld(v("IOB2")); a.anda(imm(7)); a.st(YX)
    a.far("ui_stored")
    a.label("ui_isbits")
    a.page(IOP); a.ld(v("IOB1")); a.anda(imm(0x7F)); a.st(yd(BITS7))
    a.label("ui_stored")
    a.ld(v("CNTW")); a.adda(imm(1)); a.st(v("CNTW")); a.st(v("STAT"))
    setv("BWANT", 0); call("wait_btn", "UIRET")
    a.ld(v("CNTW")); a.xora(imm(12))
    far_if_not_zero("ui_entry")
    # working: lights off, status "busy"
    setv("WLO", 0); setv("WHI", 0); setv("STAT", MODE_BUSY)
    call("frame_word", "ZRET"); call("io_show", "IORET")
    call("calc", "CALCRET")
    a.page(IOP); a.ld(yd(IDX + 22)); a.st(v("W12LO")); a.ld(yd(IDX + 23)); a.st(v("W12HI"))
    call("mkqr", "QRRET")
    # forget everything except the 12th word and the QR code
    for page in (SIO, D0, D1, D2, IOP, CIO, PAGE_S0, PAGE_S0 + 1, PAGE_W, M256):
        fill(page, 0, 128); fill(page, 128, 0)
    a.ld(imm(0))
    for cell in list(range(0x01, 0x6F)) + list(range(0x81, 0xF9)):
        a.st(zp(cell))
    # results: the 12th word, then the 41 rows; NEXT steps on, and round again
    a.label("ui_word12")
    setv("ECHO", 0); setv("WLO", v("W12LO")); setv("WHI", v("W12HI")); setv("STAT", MODE_WORD | 12)
    call("frame_word", "ZRET"); call("io_show", "IORET")
    press_and_release(BTN_NEXT)
    setv("ROWN", 0)
    a.label("ui_row")
    a.ld(v("ROWN")); a.adda(imm(1)); a.ora(imm(MODE_ROW)); a.st(v("STAT"))
    call("frame_row", "ZRET"); call("io_show", "IORET")
    press_and_release(BTN_NEXT)
    a.ld(v("ROWN")); a.adda(imm(1)); a.st(v("ROWN")); a.xora(imm(41))
    far_if_not_zero("ui_row")
    a.far("ui_word12")

# =============================================================================
# main
# =============================================================================
WORD_BYTES = b"".join(w.encode() + b"\0" for w in k.load_words())

# ---- start-up: tables and constants that last the whole run --------------------
a.nop(); a.nop()
a.ld(imm(0)); a.st(zp(ZERO)); a.ld(imm(1)); a.st(zp(ONE))
def shl1():                             # table[x] = x + x
    a.ld(v("CNT"), "X"); a.ld(v("CNT")); a.adda(AC); a.page(PAGE_SHL + 1); a.st(YX)
table_loop(shl1)
def shr1():                             # table[2i] = table[2i+1] = i
    a.ld(v("CNT")); a.adda(AC); a.ld(AC, "X"); a.page(PAGE_SHR + 1); a.ld(v("CNT")); a.st(YX)
    a.ld(v("CNT")); a.adda(AC); a.adda(imm(1)); a.ld(AC, "X"); a.ld(v("CNT")); a.st(YX)
table_loop(shr1, 128)
for base in (PAGE_SHL, PAGE_SHR):       # shift by n = shift by n-1, then by 1
    for n in range(2, 8):
        def compose(base=base, n=n):
            a.ld(v("CNT"), "X"); a.ld(imm(base + n - 1), "Y"); a.ld(YX); a.ld(AC, "X")
            a.ld(imm(base + 1), "Y"); a.ld(YX)
            a.ld(v("CNT"), "X"); a.ld(imm(base + n), "Y"); a.st(YX)
        table_loop(compose)
def edge_tables():                      # shift left by 0 = unchanged; shift right by 8 = zero
    a.ld(v("CNT"), "X"); a.page(PAGE_SHL); a.ld(v("CNT")); a.st(YX)
    a.page(PAGE_SHR + 8); a.ld(imm(0)); a.st(YX)
table_loop(edge_tables)
for cyc in range(5):                    # SHA-512 round constants
    poke(PAGE_K512 + cyc, 0, b"".join(k.K512[16 * cyc + i].to_bytes(8, "little") for i in range(16)))
poke(D1, IV512, b"".join(x.to_bytes(8, "little") for x in k.H512))
poke(PAGE_K256, 0, b"".join(x.to_bytes(4, "little") for x in k.K256))
poke(M256, IV256, b"".join(x.to_bytes(4, "little") for x in k.H256))
init_ripemd_tables()
poke(D0, BSEED, b"Bitcoin seed"); poke(D0, SALT, b"mnemonic\0\0\0\1")
poke(D2, NN, k.N.to_bytes(32, "little"))
poke(D2, NOTN, ((1 << 264) - 1 - k.N).to_bytes(33, "little"))
init_curve_small()
init_text_qr()
a.far("ui")

# ---- calc: 11 word numbers and 7 bits in, account key record out ----------------
a.label("calc")
# job 1: the 12th word. Pack 11 x 11 bits + 7 bits into 16 bytes, hash once.
setv("ACCB", 0); a.st(v("BCNT")); a.st(v("OPTR")); a.st(v("WP")); setv("OPG", M256)
a.label("ent_word")
for mask in (4, 2, 1):                  # top 3 bits of this word number
    a.ld(v("WP")); a.adda(imm(IDX + 1)); a.ld(AC, "X"); a.page(IOP); a.ld(YX); a.anda(imm(mask)); a.st(v("BITV"))
    call("putbit", "PBRET")
for mask in (128, 64, 32, 16, 8, 4, 2, 1):
    a.ld(v("WP")); a.adda(imm(IDX)); a.ld(AC, "X"); a.page(IOP); a.ld(YX); a.anda(imm(mask)); a.st(v("BITV"))
    call("putbit", "PBRET")
a.ld(v("WP")); a.adda(imm(2)); a.st(v("WP")); a.xora(imm(22))
far_if_not_zero("ent_word")
for mask in (64, 32, 16, 8, 4, 2, 1):   # the 7 coin-flip bits
    a.page(IOP); a.ld(yd(BITS7)); a.anda(imm(mask)); a.st(v("BITV"))
    call("putbit", "PBRET")
sha256(16, 64)
a.page(IOP); a.ld(yd(BITS7)); a.st(v("BITV"))       # 12th word = 7 bits, then the top 4 bits of the hash
a.ld(v("BITV"), "X"); a.page(PAGE_SHL + 4); a.ld(YX); a.st(v("ACCB"))
a.ld(zp(DG), "X"); a.page(PAGE_SHR + 4); a.ld(YX); a.ora(v("ACCB"))
a.page(IOP); a.st(yd(IDX + 22))
a.ld(v("BITV"), "X"); a.page(PAGE_SHR + 4); a.ld(YX); a.page(IOP); a.st(yd(IDX + 23))

# the words as text. The word list is unpacked into RAM, then each word is found by counting.
for i in range(0, len(WORD_BYTES), 256):
    poke(PAGE_WORDS + i // 256, 0, WORD_BYTES[i:i + 256])
setv("TLEN", 0); setv("TI", 0)
a.label("tx_word")
a.ld(v("TI")); a.adda(AC); a.adda(imm(IDX)); a.ld(AC, "X"); a.page(IOP); a.ld(YX); a.st(v("NLO"))
a.ld(v("TI")); a.adda(AC); a.adda(imm(IDX + 1)); a.ld(AC, "X"); a.ld(YX); a.st(v("NHI"))
setv("WPG", PAGE_WORDS); setv("WOF", 0)
a.label("tx_skip")                      # pass over that many words
a.ld(v("NLO")); a.ora(v("NHI"))
a.fit(8)
a.branch("bne", "tx_one"); a.nop()
a.far("tx_copy")
a.label("tx_one")
a.label("tx_scan")
call("nextch", "PBRET")
far_if_not_zero("tx_scan")
a.fit(16)
a.ld(v("NLO"))
a.branch("bne", "tx_nb"); a.nop()
a.ld(v("NHI")); a.suba(imm(1)); a.st(v("NHI"))
a.label("tx_nb")
a.ld(v("NLO")); a.suba(imm(1)); a.st(v("NLO"))
a.far("tx_skip")
a.label("tx_copy")
a.ld(v("TI"))                           # a space before every word but the first
a.fit(16)
a.branch("beq", "tx_nosp"); a.nop()
a.ld(v("TLEN"), "X"); a.ld(imm(D0), "Y"); a.ld(imm(0x20)); a.st(YX)
a.ld(v("TLEN")); a.adda(imm(1)); a.st(v("TLEN"))
a.label("tx_nosp")
a.label("tx_char")
call("nextch", "PBRET")
a.fit(8)
a.branch("bne", "tx_put"); a.nop()
a.far("tx_done")
a.label("tx_put")
a.ld(v("TLEN"), "X"); a.ld(imm(D0), "Y"); a.ld(v("BITV")); a.st(YX)
a.ld(v("TLEN")); a.adda(imm(1)); a.st(v("TLEN"))
a.far("tx_char")
a.label("tx_done")
a.ld(v("TI")); a.adda(imm(1)); a.st(v("TI")); a.xora(imm(12))
far_if_not_zero("tx_word")
a.far("calc2")
a.label("calc2")
init_mul_tables()                       # these replace the word list in RAM

# job 2: words -> seed -> master key
call("pbkdf2", "G2RET")
setv("HK_SP", D0); setv("HK_SO", BSEED); setv("HK_LEN", 12)
call("hmac_key", "GRET")
copy(D1, TACC, SIO, DIG, 64)
call("dig2blk", "HRET")
call("hmac_tail", "GRET")
copy(SIO, DIG, D2, KEY, 32, reverse=True)           # left half: the key, stored lowest byte first
copy(SIO, DIG + 32, D2, CHAIN, 32)                  # right half: the chain code
call("fingerprint", "G2RET")
a.page(D2)
for j in range(4): a.ld(zp(FPOUT + j)); a.st(yd(FPM + j))
a.page(IOP)
for j in range(4): a.ld(zp(FPOUT + j)); a.st(yd(OUT_FP + j))

for depth, step in ((1, 84), (2, 0), (3, 0)):       # m / 84' / 0' / 0'
    if depth == 3:
        call("fingerprint", "G2RET")
        a.page(D2)
        for j in range(4): a.ld(zp(FPOUT + j)); a.st(yd(FPP + j))
    setv("HK_SP", D2); setv("HK_SO", CHAIN); setv("HK_LEN", 32)
    call("hmac_key", "GRET")
    copy(D2, KEY, SIO, BLK + 1, 32, reverse=True)   # message: 0, key, 0x80, 0, 0, step
    a.page(SIO)
    a.ld(imm(0)); a.st(yd(BLK)); a.st(yd(BLK + 34)); a.st(yd(BLK + 35))
    a.ld(imm(0x80)); a.st(yd(BLK + 33)); a.st(yd(BLK + 37))
    a.ld(imm(step)); a.st(yd(BLK + 36))
    fill(SIO, BLK + 38, BLK + 126)
    a.page(SIO); a.ld(imm(0x05)); a.st(yd(BLK + 126)); a.ld(imm(0x28)); a.st(yd(BLK + 127))   # 165 bytes
    call("hmac_tail", "GRET")
    copy(SIO, DIG, D2, IL, 32, reverse=True)
    call("modn", "GRET")
    copy(SIO, DIG + 32, D2, CHAIN, 32)

copy(D2, KEY, CIO, K_OFF, 32)
call("pubkey", "PKRET")
a.page(IOP)                             # the record: depth, parent fingerprint, number, chain code, public key
a.ld(imm(3)); a.st(yd(BODY))
a.ld(imm(0x80)); a.st(yd(BODY + 5))
a.ld(imm(0)); a.st(yd(BODY + 6)); a.st(yd(BODY + 7)); a.st(yd(BODY + 8))
copy(D2, FPP, IOP, BODY + 1, 4)
copy(D2, CHAIN, IOP, BODY + 9, 32)
copy(CIO, OUT_OFF, IOP, BODY + 41, 33)
ret("CALCRET")

main_mkqr()
main_ui()


routines_helpers()
routines_sha512()
routines_curve()
routines_sha256()
routines_ripemd()
routines_glue()
routines_text_qr()
routines_module()

a.nop(); a.nop()
a.label("halt")
a.branch("bra", "halt"); a.nop()

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    open(os.path.join(here, "lock.rom"), "wb").write(a.image())
    keep = ("halt", "calc", "mkqr", "ui", "sha256", "rmd", "pubkey", "compress")
    json.dump({"labels": {n: a.labels[n] for n in keep}, "words": a.pc, "Z": Z,
               "pages": {"IOP": IOP, "M256": M256, "D0": D0, "D1": D1, "D2": D2, "SIO": SIO, "CIO": CIO,
                         "B58PG": B58PG, "DESCPG": DESCPG, "MATRIX": MATRIX},
               "off": {"IDX": IDX, "BITS7": BITS7, "OUT_FP": OUT_FP, "BODY": BODY, "DG": DG, "FPOUT": FPOUT,
                       "S_TOTAL": S_TOTAL, "R256L": R256L, "RMD_RETL": RMD["RETL"], "TEXT": TEXT, "TACC": TACC,
                       "KEY": KEY, "CHAIN": CHAIN, "H256": H256, "K": K_OFF, "OUT": OUT_OFF, "ZTXT": ZTXT}},
              open(os.path.join(here, "lock.json"), "w"), indent=1)
    print(f"ROM words used: {a.pc} of 65536 ({100 * a.pc / 65536:.0f}%)")
