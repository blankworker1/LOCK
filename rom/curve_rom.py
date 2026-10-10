#!/usr/bin/env python3
"""curve_rom.py - the curve arithmetic (private key -> public key) as native Gigatron code.

Builds a ROM image holding:
  - start-up code that fills the multiplication tables
  - 256-bit multiply, add and subtract, all modulo the curve's prime
  - a tiny interpreter that runs lists of those operations ("programs"),
    so the point formulas read the same as in keycalc.py and lock.c
  - a bit-by-bit loop used both for key * G and for the final division
  - `pubkey`: 32-byte private key in, 33-byte compressed public key out

How the multiply works. The CPU cannot multiply, shift or carry, so:
  - byte * byte is four table lookups: the multiplier is split into two
    nibbles, and tables give (nibble * byte) and (16 * nibble * byte)
  - the multiply goes one multiplier byte ("row") at a time, lowest first.
    After each row a multiple of the prime is added that makes the lowest
    byte zero, and everything moves down one byte (Montgomery's method).
    The running value never needs more than 33 bytes.
  - numbers are therefore kept in "Montgomery form" (times 2^256) inside
    the machine and converted back at the very end.

RAM pages: 1 input/output, 2-3 programs, 4-5 number slots, 6 working
buffers, 7-13 small tables and constants, 16-79 multiplication tables.
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference"))
import keycalc as k
from gtasm import Asm, imm, zp, IX, yd, YX, AC

a = Asm()

# ---- page zero ----------------------------------------------------------
ZERO, ONE = 0x00, 0x80                  # hold 0 and 1: used to turn a top bit into a carry
A_, B_, LO, HI = 0x01, 0x21, 0x41, 0x81  # 32-byte areas: multiplier, multiplicand, row products
Z = {}
for i, n in enumerate("TMP SUMTMP CSAVE Q NQ NS1 NS2 PLL PHL PLH PHH AP ROWCNT RSRC RIP CNT MTMP "
                      "K_FF K_D0 K_03 K_2F K_FC K_FE K_D1 CSP CSO CDP CDO CCNT RET0L RET0H".split()):
    Z[n] = 0x61 + i
for i, n in enumerate("RET1L RET1H RET2L RET2H RET3L RET3H RETBL RETBH IPP IPO OPC DPG DOF APG AOF BPG BOF "
                      "KP KO BYTEI KBYTE MASK STARTED PI_P PI_O PE_P PE_O PS_P PS_O "
                      "T1L T1H T2L T2H TDL TDH TA0 TA1 TB0 TB1 TC0 TC1 V0 V1 V2".split()):
    Z[n] = 0xA1 + i
assert max(Z.values()) <= 0xFF and 0x61 + 31 <= 0x80
def v(name): return zp(Z[name])

# ---- RAM pages ------------------------------------------------------------
PAGE_IO, PAGE_BC0, PAGE_BC1, PAGE_S0, PAGE_W = 1, 2, 3, 4, 6
PAGE_QT, PAGE_S1N, PAGE_S2N, PAGE_HN, PAGE_TMP1, PAGE_TMP2, PAGE_CONST = 7, 8, 9, 10, 11, 12, 13
PAGE_ML, PAGE_MH, PAGE_ML16, PAGE_MH16 = 16, 32, 48, 64
K_OFF, OUT_OFF, SCRATCH_OFF = 0x00, 0x20, 0x80       # in the input/output page
ACC, T = 0x00, 0x40                                  # in the working page: 33 and 34 bytes

SLOTS = "PX PY PZ t1 t2 t3 t4 t5 t6 GX GY ONEM ONE1 IA IR X1".split()
def slot(name):
    s = SLOTS.index(name)
    return PAGE_S0 + s // 8, (s % 8) * 32

# ---- building blocks --------------------------------------------------------
def setv(name, val):
    a.ld(val if isinstance(val, tuple) else imm(val)); a.st(v(name))

def call(label, ret):
    """Jump to a routine, leaving the way back in two page-zero bytes."""
    back = f"r{a.pc}"
    a.ld(imm(("lo", back))); a.st(v(ret + "L"))
    a.ld(imm(("hi", back))); a.st(v(ret + "H"))
    a.far(label)
    a.label(back)

def ret(name): a.jump_via(Z[name + "H"], Z[name + "L"])

def carry(x, y):
    """AC holds x + y (+ carry in), already stored. Leaves the carry out (0 or 1) in AC.
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
    return keep

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
        a.st(v("SUMTMP") if inplace else dst[j])
        carry(x[j], y[j])
        if inplace:
            a.ld(v("SUMTMP")); a.st(dst[j])
        a.ld(IX)                        # AC = memory[0x00] = 0 or memory[0x80] = 1

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

def copy(sp, so, dp, do):
    setv("CSP", sp); setv("CSO", so); setv("CDP", dp); setv("CDO", do)
    call("copy32", "RET0")

# ---- programs: the point formulas, as lists of (operation, result, x, y) ------
END, MUL, ADD, SUB, MOV = 0, 1, 2, 3, 4
PROGRAMS = {
    "DOUBLE": [                         # same steps as pt_double() in lock.c
        (MUL, "t1", "PX", "PX"), (MUL, "t2", "PY", "PY"), (MUL, "t3", "t2", "t2"),
        (ADD, "t4", "PX", "t2"), (MUL, "t4", "t4", "t4"), (SUB, "t4", "t4", "t1"),
        (SUB, "t4", "t4", "t3"), (ADD, "t4", "t4", "t4"),
        (ADD, "t5", "t1", "t1"), (ADD, "t5", "t5", "t1"), (MUL, "t6", "t5", "t5"),
        (MUL, "PZ", "PY", "PZ"), (ADD, "PZ", "PZ", "PZ"),
        (SUB, "PX", "t6", "t4"), (SUB, "PX", "PX", "t4"),
        (SUB, "t4", "t4", "PX"), (MUL, "t4", "t5", "t4"),
        (ADD, "t3", "t3", "t3"), (ADD, "t3", "t3", "t3"), (ADD, "t3", "t3", "t3"),
        (SUB, "PY", "t4", "t3")],
    "ADDG": [                           # same steps as pt_add_g() in lock.c
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
    "FINAL": [                          # x = X/Z^2, y = Y/Z^3, then out of Montgomery form
        (MUL, "t2", "IR", "IR"), (MUL, "PX", "PX", "t2"),
        (MUL, "t2", "IR", "t2"), (MUL, "PY", "PY", "t2"),
        (MUL, "PX", "PX", "ONE1"), (MUL, "PY", "PY", "ONE1")],
}
PROG_AT, bc = {}, {PAGE_BC0: bytearray(), PAGE_BC1: bytearray()}
for name, steps in PROGRAMS.items():
    code = bytearray()
    for op, d, x, y in steps:
        code += bytes([op, *slot(d), *slot(x), *slot(y)])
    code.append(END)
    page = PAGE_BC0 if len(bc[PAGE_BC0]) + len(code) <= 256 else PAGE_BC1
    assert len(bc[page]) + len(code) <= 256
    PROG_AT[name] = (page, len(bc[page]))
    bc[page] += code

def run(name):
    setv("IPP", PROG_AT[name][0]); setv("IPO", PROG_AT[name][1])
    call("interp", "RET2")

# =========================================================================
# start-up
# =========================================================================
a.nop(); a.nop()
setv("TMP", 0); a.st(zp(ZERO)); a.ld(imm(1)); a.st(zp(ONE))
for name, val in (("K_FF", 0xFF), ("K_D0", 0xD0), ("K_03", 0x03), ("K_2F", 0x2F),
                  ("K_FC", 0xFC), ("K_FE", 0xFE), ("K_D1", 0xD1)):
    setv(name, val)

# high-nibble table: x >> 4, built as (x >> 1) applied four times
def shr1():                             # table[2i] = table[2i+1] = i
    a.ld(v("CNT")); a.adda(AC); a.ld(AC, "X"); a.page(PAGE_TMP1); a.ld(v("CNT")); a.st(YX)
    a.ld(v("CNT")); a.adda(AC); a.adda(imm(1)); a.ld(AC, "X"); a.ld(v("CNT")); a.st(YX)
table_loop(shr1, 128)
def compose(dst, f, g):                 # dst[x] = f[g[x]]
    def body():
        a.ld(v("CNT"), "X"); a.ld(imm(g), "Y"); a.ld(YX); a.ld(AC, "X")
        a.ld(imm(f), "Y"); a.ld(YX)
        a.ld(v("CNT"), "X"); a.ld(imm(dst), "Y"); a.st(YX)
    table_loop(body)
compose(PAGE_TMP2, PAGE_TMP1, PAGE_TMP1)
compose(PAGE_HN, PAGE_TMP2, PAGE_TMP2)

# multiplication tables. Entry x of table n holds n*x (low byte page, high byte page).
def zero_and_identity():
    a.ld(v("CNT"), "X")
    a.ld(imm(0))
    for page in (PAGE_ML, PAGE_MH, PAGE_MH + 1, PAGE_ML16, PAGE_MH16):
        a.ld(imm(page), "Y"); a.st(YX)
    a.ld(imm(PAGE_ML + 1), "Y"); a.ld(v("CNT")); a.st(YX)
table_loop(zero_and_identity)
def table_add(dl, dh, s1l, s1h, s2l, s2h):   # table d = table s1 + table s2, entry by entry
    for name, page in (("TDL", dl), ("TDH", dh), ("T1L", s1l), ("T1H", s1h), ("T2L", s2l), ("T2H", s2h)):
        setv(name, page)
    call("tadd", "RET0")
for n in range(2, 16):                  # n*x = (n-1)*x + x
    table_add(PAGE_ML + n, PAGE_MH + n, PAGE_ML + n - 1, PAGE_MH + n - 1, PAGE_ML + 1, PAGE_MH + 1)
table_add(PAGE_ML16 + 1, PAGE_MH16 + 1, PAGE_ML + 15, PAGE_MH + 15, PAGE_ML + 1, PAGE_MH + 1)   # 16x = 15x + x
for n in range(2, 16):                  # 16n*x = 16(n-1)*x + 16x
    table_add(PAGE_ML16 + n, PAGE_MH16 + n, PAGE_ML16 + n - 1, PAGE_MH16 + n - 1, PAGE_ML16 + 1, PAGE_MH16 + 1)

# q table: the multiple of the prime that clears a low byte t is q = t * 0x31 (mod 256)
setv("V0", 0)
def qtable():
    a.ld(v("CNT"), "X"); a.page(PAGE_QT); a.ld(v("V0")); a.st(YX)
    a.adda(imm(0x31)); a.st(v("V0"))
table_loop(qtable)
# for each q: bytes 1 and 2 of q * 0x3D1, stored inverted ready for subtracting
setv("V0", 0); a.st(v("V1")); a.st(v("V2"))
def stable():
    a.ld(v("CNT"), "X")
    a.page(PAGE_S1N); a.ld(v("V1")); a.xora(imm(0xFF)); a.st(YX)
    a.page(PAGE_S2N); a.ld(v("V2")); a.xora(imm(0xFF)); a.st(YX)
    add([v("V0"), v("V1"), v("V2")], [v("V0"), v("V1"), v("V2")], [v("K_D1"), v("K_03"), zp(ZERO)])
table_loop(stable)

# constants: base point and one (Montgomery form), plain one, the exponent prime-2, the programs
R = 1 << 256
def le(n): return n.to_bytes(32, "little")
for name, val in (("GX", k.GX * R % k.P), ("GY", k.GY * R % k.P), ("ONEM", R % k.P), ("ONE1", 1)):
    poke(*slot(name), le(val))
poke(PAGE_CONST, 0, le(k.P - 2))
for page, code in bc.items():
    poke(page, 0, code)
a.far("halt")

# table d = table s1 + table s2 (16-bit entries), pages given in page zero
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

# =========================================================================
# copy32: 32 bytes from (page CSP, offset CSO) to (page CDP, offset CDO)
# =========================================================================
a.label("copy32")
setv("CCNT", 32)
a.fit(24)
a.label("cp")
a.ld(v("CSO"), "X"); a.ld(v("CSP"), "Y"); a.ld(YX)
a.ld(v("CDO"), "X"); a.ld(v("CDP"), "Y"); a.st(YX)
a.ld(v("CSO")); a.adda(imm(1)); a.st(v("CSO"))
a.ld(v("CDO")); a.adda(imm(1)); a.st(v("CDO"))
a.ld(v("CCNT")); a.suba(imm(1)); a.st(v("CCNT"))
a.branch("bne", "cp"); a.nop()
ret("RET0")

# =========================================================================
# fe_mul: working value = A * B / 2^256 mod prime (A, B in page zero)
# =========================================================================
a.label("fe_mul")
a.page(PAGE_W); a.ld(imm(0))
for j in range(33): a.st(yd(ACC + j))
setv("AP", A_); setv("ROWCNT", 32)
a.label("row")
# this row's multiplier byte picks four table pages: low nibble, and 16 * high nibble
a.ld(v("AP"), "X"); a.ld(IX); a.st(v("MTMP"))
a.anda(imm(15)); a.adda(imm(PAGE_ML)); a.st(v("PLL"))
a.ld(v("MTMP")); a.anda(imm(15)); a.adda(imm(PAGE_MH)); a.st(v("PHL"))
a.ld(v("MTMP"), "X"); a.page(PAGE_HN)
a.ld(YX); a.adda(imm(PAGE_ML16)); a.st(v("PLH"))
a.ld(YX); a.adda(imm(PAGE_MH16)); a.st(v("PHH"))
# multiplier byte * each byte of B -> exact 16-bit products in LO, HI
for j in range(32):
    a.ld(zp(B_ + j), "X")
    a.ld(v("PLL"), "Y"); a.ld(YX); a.st(v("TMP"))
    a.ld(v("PLH"), "Y"); a.adda(YX); a.st(zp(LO + j))
    carry(v("TMP"), YX); a.ld(IX)
    a.ld(zp(B_ + j), "X")
    a.ld(v("PHL"), "Y"); a.adda(YX)
    a.ld(v("PHH"), "Y"); a.adda(YX); a.st(zp(HI + j))
# first sum: T = ACC + LO, and q * 2^256 on top, where q is chosen from T's lowest byte
a.page(PAGE_W)
add([yd(T)], [yd(ACC)], [zp(LO)], cout=True)
a.st(v("CSAVE"))
a.ld(yd(T)); a.ld(AC, "X")
a.page(PAGE_QT); a.ld(YX); a.st(v("Q")); a.ld(AC, "X")
a.xora(imm(0xFF)); a.st(v("NQ"))
a.page(PAGE_S1N); a.ld(YX); a.st(v("NS1"))
a.page(PAGE_S2N); a.ld(YX); a.st(v("NS2"))
a.page(PAGE_W); a.ld(v("CSAVE"))
add([yd(T + j) for j in range(1, 32)], [yd(ACC + j) for j in range(1, 32)],
    [zp(LO + j) for j in range(1, 32)], cin="ac", cout=True)
a.adda(yd(ACC + 32)); a.st(v("TMP")); a.adda(v("Q")); a.st(yd(T + 32))
carry(v("TMP"), v("Q")); a.ld(IX); a.st(yd(T + 33))
# second sum, moved down one byte: ACC = (T + HI * 256) / 256
add([yd(ACC + j) for j in range(32)], [yd(T + 1 + j) for j in range(32)],
    [zp(HI + j) for j in range(32)], cout=True)
a.adda(yd(T + 33)); a.st(yd(ACC + 32))
# take away q * (2^32 + 977): five bytes, then pass any borrow upward
add([yd(ACC + j) for j in range(5)], [yd(ACC + j) for j in range(5)],
    [v("NS1"), v("NS2"), v("K_FF"), v("NQ"), v("K_FF")], cin=1, cout=True)
a.fit(24)
a.branch("bne", "rip_done")             # carry 1 = no borrow: finished
a.ld(imm(ACC + 5))
a.st(v("RIP"))
a.label("rip"); a.y = PAGE_W
a.ld(v("RIP"), "X"); a.ld(YX)
a.branch("beq", "rip_zero")
a.suba(imm(1))
a.st(YX)                                # byte was not zero: take one off and stop
a.branch("bra", "rip_done"); a.nop()
a.label("rip_zero"); a.y = PAGE_W
a.st(YX)                                # byte was zero: becomes 0xFF, borrow continues
a.ld(v("RIP")); a.adda(imm(1)); a.st(v("RIP"))
a.branch("bra", "rip"); a.nop()
a.label("rip_done"); a.y = PAGE_W
a.ld(v("AP")); a.adda(imm(1)); a.st(v("AP"))
a.ld(v("ROWCNT")); a.suba(imm(1)); a.st(v("ROWCNT"))
a.fit(8)
a.branch("beq", "fe_tail"); a.nop()
a.far("row")
# the value in ACC is below twice the prime: subtract the prime once if needed
a.label("fe_tail")
a.page(PAGE_W)
NOT_P = [v("K_D0"), v("K_03"), zp(ZERO), zp(ZERO), zp(ONE)] + [zp(ZERO)] * 27 + [v("K_FF")]
add([yd(T + j) for j in range(33)], [yd(ACC + j) for j in range(33)], NOT_P, cin=1, cout=True)
a.fit(6)
a.branch("beq", "tail_sel")             # carry 0: ACC was below the prime, keep it
a.ld(imm(ACC))
a.ld(imm(T))
a.label("tail_sel")
a.st(v("RSRC"))
ret("RET1")

# fe_add: working value = A + B mod prime
a.label("fe_add")
a.page(PAGE_W)
add([yd(ACC + j) for j in range(32)], [zp(A_ + j) for j in range(32)], [zp(B_ + j) for j in range(32)], cout=True)
a.st(yd(ACC + 32))
a.far("fe_tail")

# fe_sub: working value = A - B mod prime
a.label("fe_sub")
for j in range(32):
    a.ld(zp(B_ + j)); a.xora(imm(0xFF)); a.st(zp(LO + j))
a.page(PAGE_W)
add([yd(ACC + j) for j in range(32)], [zp(A_ + j) for j in range(32)], [zp(LO + j) for j in range(32)], cin=1, cout=True)
a.st(v("CSAVE"))
P_BYTES = [v("K_2F"), v("K_FC"), v("K_FF"), v("K_FF"), v("K_FE")] + [v("K_FF")] * 27
add([yd(T + j) for j in range(32)], [yd(ACC + j) for j in range(32)], P_BYTES)
a.ld(v("CSAVE"))
a.fit(6)
a.branch("beq", "sub_sel")              # carry 0: went below zero, use ACC + prime
a.ld(imm(T))
a.ld(imm(ACC))
a.label("sub_sel")
a.st(v("RSRC"))
ret("RET1")

# =========================================================================
# interp: run a program of (operation, result, x, y) steps
# =========================================================================
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
copy(PAGE_W, v("RSRC"), v("DPG"), v("DOF"))
a.far("interp")
a.label("i_mov")
copy(v("APG"), v("AOF"), v("DPG"), v("DOF"))
a.far("interp")

# =========================================================================
# bitloop: walk a 256-bit number from the top bit down.
# Until the first 1 bit nothing happens; that bit runs the "first" program.
# After that every bit runs "every", and each 1 bit also runs "set".
# =========================================================================
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

# =========================================================================
# pubkey: 32-byte key at the input area (lowest byte first) -> 33 bytes at the output area
# =========================================================================
a.label("pubkey")
setv("KP", PAGE_IO); setv("KO", K_OFF)
set_programs("INITG", "DOUBLE", "ADDG")
call("bitloop", "RET3")                 # the point key * G, as X, Y, Z
run("PRE_INV")
setv("KP", PAGE_CONST); setv("KO", 0)
set_programs("INV_INIT", "INV_SQR", "INV_MUL")
call("bitloop", "RET3")                 # 1/Z, by raising Z to the power prime-2
run("FINAL")
px, py = slot("PX"), slot("PY")
assert px[0] == py[0]
a.page(px[0])
a.ld(yd(py[1])); a.anda(imm(1)); a.adda(imm(2)); a.st(v("TMP"))
for i in range(32):
    a.ld(yd(px[1] + 31 - i)); a.st(zp(A_ + i))
a.page(PAGE_IO)
a.ld(v("TMP")); a.st(yd(OUT_OFF))
for i in range(32):
    a.ld(zp(A_ + i)); a.st(yd(OUT_OFF + 1 + i))
a.far("halt")

# test entry: run the program that IPP/IPO point at, then stop
a.label("run_prog")
call("interp", "RET2")
a.far("halt")

a.nop(); a.nop()
a.label("halt")
a.branch("bra", "halt"); a.nop()

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    open(os.path.join(here, "curve.rom"), "wb").write(a.image())
    json.dump({"labels": {n: p for n, p in a.labels.items() if n[0] not in "njtr" or n in ("row", "run_prog")},
               "words": a.pc, "Z": Z, "slots": {s: slot(s) for s in SLOTS},
               "IO": PAGE_IO * 256, "K": PAGE_IO * 256 + K_OFF, "OUT": PAGE_IO * 256 + OUT_OFF,
               "SCRATCH": [PAGE_IO, SCRATCH_OFF], "ops": {"END": END, "MUL": MUL, "ADD": ADD, "SUB": SUB, "MOV": MOV}},
              open(os.path.join(here, "curve.json"), "w"), indent=1)
    print(f"ROM words used: {a.pc} of 65536 ({100 * a.pc / 65536:.1f}%)")
