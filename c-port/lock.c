/* lock.c - the whole LOCK calculation in C (C89).
 *
 * In : 11 word numbers (0-2047) and 7 coin-flip bits (as a number 0-127).
 * Out: the 12th word, the fingerprint, the xpub and zpub at m/84'/0'/0',
 *      and the descriptor as a 41 x 41 QR code, one row per line.
 *
 * A routine-for-routine translation of keycalc.py. The same file builds
 * for a PC (to check it against keycalc.py quickly) and for the Gigatron
 * (GLCC compiler), where int is 16 bits and long is 32 bits.
 *
 * TEST VECTORS ONLY: never enter a real seed on a networked computer.
 */
#include <stdio.h>

#ifdef __gigatron__
#include <time.h>
typedef unsigned long u32;          /* 32 bits on the Gigatron */
typedef unsigned int u16;           /* 16 bits on the Gigatron */
#define TICKS() ((long)clock())     /* sixtieths of a second */
#else
typedef unsigned int u32;
typedef unsigned short u16;
#define TICKS() 0L
#endif
typedef unsigned char u8;
typedef struct { u32 hi, lo; } u64; /* no 64-bit type: two halves */

#include "tables.h"

static void stage(const char *name) { printf("# %ld %s\n", TICKS(), name); }

/* ------------------------------------------------------------- SHA-256 */
#define ROTR(x,n) (((x) >> (n)) | ((x) << (32 - (n))))
#define ROTL(x,n) (((x) << (n)) | ((x) >> (32 - (n))))

static u32 w32[64], h32[8];
static u8 pad[128];

static void sha256_compress(const u8 *p)
{
  u32 a, b, c, d, e, f, g, h, t1, t2, x;
  int i;
  for (i = 0; i < 16; i++, p += 4)
    w32[i] = ((u32)p[0] << 24) | ((u32)p[1] << 16) | ((u32)p[2] << 8) | p[3];
  for (i = 16; i < 64; i++) {
    x = w32[i-15]; t1 = ROTR(x,7) ^ ROTR(x,18) ^ (x >> 3);
    x = w32[i-2];  t2 = ROTR(x,17) ^ ROTR(x,19) ^ (x >> 10);
    w32[i] = w32[i-16] + t1 + w32[i-7] + t2;
  }
  a=h32[0]; b=h32[1]; c=h32[2]; d=h32[3]; e=h32[4]; f=h32[5]; g=h32[6]; h=h32[7];
  for (i = 0; i < 64; i++) {
    t1 = h + (ROTR(e,6) ^ ROTR(e,11) ^ ROTR(e,25)) + ((e & f) ^ (~e & g)) + K256[i] + w32[i];
    t2 = (ROTR(a,2) ^ ROTR(a,13) ^ ROTR(a,22)) + ((a & b) ^ (a & c) ^ (b & c));
    h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
  }
  h32[0]+=a; h32[1]+=b; h32[2]+=c; h32[3]+=d; h32[4]+=e; h32[5]+=f; h32[6]+=g; h32[7]+=h;
}

/* msg of up to 119 bytes -> 32 bytes */
static void sha256(const u8 *msg, int len, u8 *out)
{
  int i, total = (len < 56) ? 64 : 128;
  for (i = 0; i < 128; i++) pad[i] = 0;
  for (i = 0; i < len; i++) pad[i] = msg[i];
  pad[len] = 0x80;
  pad[total-2] = (u8)((len * 8) >> 8);
  pad[total-1] = (u8)(len * 8);
  for (i = 0; i < 8; i++) h32[i] = H256[i];
  for (i = 0; i < total; i += 64) sha256_compress(pad + i);
  for (i = 0; i < 8; i++) {
    out[4*i] = (u8)(h32[i] >> 24); out[4*i+1] = (u8)(h32[i] >> 16);
    out[4*i+2] = (u8)(h32[i] >> 8); out[4*i+3] = (u8)h32[i];
  }
}

/* ------------------------------------------------------------- SHA-512 */
static u64 w64[80], h64[8], v64[8];
static u8 b512[128];

static void add64(u64 *a, const u64 *b)
{ u32 lo = a->lo + b->lo; a->hi += b->hi + (lo < a->lo); a->lo = lo; }

static void rotr64(u64 *r, const u64 *x, int n)     /* 0 < n < 64, n not 32 */
{
  u32 hi = x->hi, lo = x->lo, t;
  if (n > 32) { t = hi; hi = lo; lo = t; n -= 32; }
  r->lo = (lo >> n) | (hi << (32 - n));
  r->hi = (hi >> n) | (lo << (32 - n));
}
static void shr64(u64 *r, const u64 *x, int n)      /* 0 < n < 32 */
{ r->lo = (x->lo >> n) | (x->hi << (32 - n)); r->hi = x->hi >> n; }

static void sha512_compress(void)                   /* block in b512, state in h64 */
{
  static u64 t1, t2, s, u;
  int i, j;
  u8 *p = b512;
  for (i = 0; i < 16; i++, p += 8) {
    w64[i].hi = ((u32)p[0]<<24) | ((u32)p[1]<<16) | ((u32)p[2]<<8) | p[3];
    w64[i].lo = ((u32)p[4]<<24) | ((u32)p[5]<<16) | ((u32)p[6]<<8) | p[7];
  }
  for (i = 16; i < 80; i++) {
    rotr64(&s,&w64[i-15],1); rotr64(&u,&w64[i-15],8); s.hi^=u.hi; s.lo^=u.lo;
    shr64(&u,&w64[i-15],7); s.hi^=u.hi; s.lo^=u.lo;
    w64[i] = w64[i-16]; add64(&w64[i],&s); add64(&w64[i],&w64[i-7]);
    rotr64(&s,&w64[i-2],19); rotr64(&u,&w64[i-2],61); s.hi^=u.hi; s.lo^=u.lo;
    shr64(&u,&w64[i-2],6); s.hi^=u.hi; s.lo^=u.lo;
    add64(&w64[i],&s);
  }
  for (j = 0; j < 8; j++) v64[j] = h64[j];
  for (i = 0; i < 80; i++) {
    rotr64(&s,&v64[4],14); rotr64(&u,&v64[4],18); s.hi^=u.hi; s.lo^=u.lo;
    rotr64(&u,&v64[4],41); s.hi^=u.hi; s.lo^=u.lo;
    t1 = v64[7]; add64(&t1,&s);
    s.hi = (v64[4].hi & v64[5].hi) ^ (~v64[4].hi & v64[6].hi);
    s.lo = (v64[4].lo & v64[5].lo) ^ (~v64[4].lo & v64[6].lo);
    add64(&t1,&s); add64(&t1,&K512[i]); add64(&t1,&w64[i]);
    rotr64(&t2,&v64[0],28); rotr64(&u,&v64[0],34); t2.hi^=u.hi; t2.lo^=u.lo;
    rotr64(&u,&v64[0],39); t2.hi^=u.hi; t2.lo^=u.lo;
    s.hi = (v64[0].hi & v64[1].hi) ^ (v64[0].hi & v64[2].hi) ^ (v64[1].hi & v64[2].hi);
    s.lo = (v64[0].lo & v64[1].lo) ^ (v64[0].lo & v64[2].lo) ^ (v64[1].lo & v64[2].lo);
    add64(&t2,&s);
    v64[7]=v64[6]; v64[6]=v64[5]; v64[5]=v64[4]; v64[4]=v64[3]; add64(&v64[4],&t1);
    v64[3]=v64[2]; v64[2]=v64[1]; v64[1]=v64[0]; v64[0]=t1; add64(&v64[0],&t2);
  }
  for (j = 0; j < 8; j++) add64(&h64[j],&v64[j]);
}

/* -------------------------------------------- keyed SHA-512 (HMAC), PBKDF2 */
static u64 ipad[8], opad[8];
static u8 dig[64];

static void digest512(u8 *out)
{
  int i;
  for (i = 0; i < 8; i++) {
    out[8*i]   = (u8)(h64[i].hi >> 24); out[8*i+1] = (u8)(h64[i].hi >> 16);
    out[8*i+2] = (u8)(h64[i].hi >> 8);  out[8*i+3] = (u8)h64[i].hi;
    out[8*i+4] = (u8)(h64[i].lo >> 24); out[8*i+5] = (u8)(h64[i].lo >> 16);
    out[8*i+6] = (u8)(h64[i].lo >> 8);  out[8*i+7] = (u8)h64[i].lo;
  }
}

/* The two pad states: computed once per key, then reused. key up to 128 bytes */
static void hmac_key(const u8 *key, int len)
{
  int i;
  for (i = 0; i < 128; i++) b512[i] = (u8)((i < len ? key[i] : 0) ^ 0x36);
  for (i = 0; i < 8; i++) h64[i] = H512[i];
  sha512_compress();
  for (i = 0; i < 8; i++) ipad[i] = h64[i];
  for (i = 0; i < 128; i++) b512[i] = (u8)((i < len ? key[i] : 0) ^ 0x5C);
  for (i = 0; i < 8; i++) h64[i] = H512[i];
  sha512_compress();
  for (i = 0; i < 8; i++) opad[i] = h64[i];
}

/* msg of up to 111 bytes -> 64 bytes. Two passes: inner, then outer. */
static void hmac(const u8 *msg, int len, u8 *out)
{
  int i, bits = (128 + len) * 8;
  for (i = 0; i < len; i++) b512[i] = msg[i];
  b512[len] = 0x80;
  for (i = len + 1; i < 126; i++) b512[i] = 0;
  b512[126] = (u8)(bits >> 8); b512[127] = (u8)bits;
  for (i = 0; i < 8; i++) h64[i] = ipad[i];
  sha512_compress();
  digest512(dig);
  for (i = 0; i < 64; i++) b512[i] = dig[i];
  b512[64] = 0x80;
  for (i = 65; i < 126; i++) b512[i] = 0;
  b512[126] = 6; b512[127] = 0;                     /* 192 bytes = 1536 bits */
  for (i = 0; i < 8; i++) h64[i] = opad[i];
  sha512_compress();
  digest512(out);
}

static u8 U[64], T[64];

/* the 2,048 rounds: words as text -> 64-byte seed in T */
static void pbkdf2(const u8 *text, int len)
{
  static const u8 salt[12] = { 'm','n','e','m','o','n','i','c', 0,0,0,1 };
  int i, j;
  hmac_key(text, len);
  hmac(salt, 12, U);
  for (j = 0; j < 64; j++) T[j] = U[j];
  for (i = 1; i < 2048; i++) {
    hmac(U, 64, U);
    for (j = 0; j < 64; j++) T[j] ^= U[j];
    if ((i & 255) == 0) stage("  256 rounds");
  }
}

/* ----------------------------------------------------------- RIPEMD-160 */
static u32 rmd_f(int j, u32 x, u32 y, u32 z)
{
  switch (j) {
  case 0: return x ^ y ^ z;
  case 1: return (x & y) | (~x & z);
  case 2: return (x | ~y) ^ z;
  case 3: return (x & z) | (y & ~z);
  }
  return x ^ (y | ~z);
}

/* exactly 32 bytes in -> 20 bytes out */
static void ripemd160_32(const u8 *msg, u8 *out)
{
  static u32 x[16], h[5];
  u32 al, bl, cl, dl, el, ar, br, cr, dr, er, t;
  int i, r;
  for (i = 0; i < 64; i++) pad[i] = 0;
  for (i = 0; i < 32; i++) pad[i] = msg[i];
  pad[32] = 0x80; pad[57] = 1;                      /* length 256 bits, low byte first */
  for (i = 0; i < 16; i++)
    x[i] = pad[4*i] | ((u32)pad[4*i+1] << 8) | ((u32)pad[4*i+2] << 16) | ((u32)pad[4*i+3] << 24);
  h[0]=0x67452301UL; h[1]=0xEFCDAB89UL; h[2]=0x98BADCFEUL; h[3]=0x10325476UL; h[4]=0xC3D2E1F0UL;
  al=ar=h[0]; bl=br=h[1]; cl=cr=h[2]; dl=dr=h[3]; el=er=h[4];
  for (r = 0; r < 5; r++)
    for (i = 0; i < 16; i++) {
      t = al + rmd_f(r, bl, cl, dl) + x[RL[r][i]] + KL[r];
      t = ROTL(t, SL[r][i]) + el;
      al = el; el = dl; dl = ROTL(cl, 10); cl = bl; bl = t;
      t = ar + rmd_f(4 - r, br, cr, dr) + x[RR[r][i]] + KR[r];
      t = ROTL(t, SR[r][i]) + er;
      ar = er; er = dr; dr = ROTL(cr, 10); cr = br; br = t;
    }
  t = h[1] + cl + dr; h[1] = h[2] + dl + er; h[2] = h[3] + el + ar;
  h[3] = h[4] + al + br; h[4] = h[0] + bl + cr; h[0] = t;
  for (i = 0; i < 5; i++) {
    out[4*i] = (u8)h[i]; out[4*i+1] = (u8)(h[i] >> 8);
    out[4*i+2] = (u8)(h[i] >> 16); out[4*i+3] = (u8)(h[i] >> 24);
  }
}

/* ---------------------------------------- 256-bit numbers (16 pieces of 16 bits) */
static int ge(const u16 *a, const u16 *b)            /* a >= b ? */
{
  int i;
  for (i = 15; i >= 0; i--) if (a[i] != b[i]) return a[i] > b[i];
  return 1;
}
static u16 addn(u16 *r, const u16 *a, const u16 *b)  /* returns the carry */
{
  u32 c = 0; int i;
  for (i = 0; i < 16; i++) { c += (u32)a[i] + b[i]; r[i] = (u16)c; c >>= 16; }
  return (u16)c;
}
static u16 subn(u16 *r, const u16 *a, const u16 *b)  /* returns the borrow */
{
  u32 t, br = 0; int i;
  for (i = 0; i < 16; i++) { t = (u32)a[i] - b[i] - br; r[i] = (u16)t; br = (t >> 16) & 1; }
  return (u16)br;
}
static void fe_add(u16 *r, const u16 *a, const u16 *b)
{ if (addn(r, a, b) || ge(r, FP)) subn(r, r, FP); }
static void fe_sub(u16 *r, const u16 *a, const u16 *b)
{ if (subn(r, a, b)) addn(r, r, FP); }

static u16 prod[36], high[20];

/* r = a * b mod the field prime. The prime is 2^256 - 2^32 - 977, so the
 * top half folds back in as (top * 977) + (top shifted up 32 bits). */
static void fe_mul(u16 *r, const u16 *a, const u16 *b)
{
  int i, j, n, nh;
  u32 t, c, ai;
  for (i = 0; i < 36; i++) prod[i] = 0;
  for (i = 0; i < 16; i++) {
    ai = a[i]; c = 0;
    for (j = 0; j < 16; j++) {
      t = ai * b[j] + prod[i+j] + c;
      prod[i+j] = (u16)t; c = t >> 16;
    }
    prod[i+16] = (u16)c;
  }
  n = 32;
  while (n > 16) {
    nh = n - 16;
    for (i = 0; i < nh; i++) { high[i] = prod[16+i]; prod[16+i] = 0; }
    c = 0;
    for (i = 0; i < 20; i++) {
      t = prod[i] + c;
      if (i < nh) t += (u32)high[i] * 977;
      if (i >= 2 && i - 2 < nh) t += high[i-2];
      prod[i] = (u16)t; c = t >> 16;
    }
    for (n = 20; n > 16 && prod[n-1] == 0; n--) ;
  }
  for (i = 0; i < 16; i++) r[i] = prod[i];
  if (ge(r, FP)) subn(r, r, FP);
}

static u16 inv_r[16];
/* r = 1/a by Fermat: a^(prime-2), plain square-and-multiply */
static void fe_inv(u16 *r, const u16 *a)
{
  int i;
  for (i = 0; i < 16; i++) inv_r[i] = 0;
  inv_r[0] = 1;
  for (i = 255; i >= 0; i--) {
    fe_mul(inv_r, inv_r, inv_r);
    if ((FP2[i >> 4] >> (i & 15)) & 1) fe_mul(inv_r, inv_r, a);
  }
  for (i = 0; i < 16; i++) r[i] = inv_r[i];
}

/* ------------------------------------------------------ the curve secp256k1 */
static u16 PX[16], PY[16], PZ[16];                  /* the running point */
static u16 t1[16], t2[16], t3[16], t4[16], t5[16], t6[16];

static void pt_double(void)
{
  fe_mul(t1, PX, PX);                               /* a = x^2 */
  fe_mul(t2, PY, PY);                               /* b = y^2 */
  fe_mul(t3, t2, t2);                               /* c = b^2 */
  fe_add(t4, PX, t2); fe_mul(t4, t4, t4);
  fe_sub(t4, t4, t1); fe_sub(t4, t4, t3); fe_add(t4, t4, t4);   /* d */
  fe_add(t5, t1, t1); fe_add(t5, t5, t1);           /* e = 3a */
  fe_mul(t6, t5, t5);                               /* e^2 */
  fe_mul(PZ, PY, PZ); fe_add(PZ, PZ, PZ);           /* z = 2yz */
  fe_sub(PX, t6, t4); fe_sub(PX, PX, t4);           /* x = e^2 - 2d */
  fe_sub(t4, t4, PX); fe_mul(t4, t5, t4);
  fe_add(t3, t3, t3); fe_add(t3, t3, t3); fe_add(t3, t3, t3);   /* 8c */
  fe_sub(PY, t4, t3);                               /* y = e(d - x) - 8c */
}

static void pt_add_g(void)                          /* add the fixed base point */
{
  int i;
  fe_mul(t1, PZ, PZ);                               /* zz */
  fe_mul(t2, GX, t1); fe_sub(t2, t2, PX);           /* h */
  fe_mul(t3, PZ, t1); fe_mul(t3, GY, t3); fe_sub(t3, t3, PY);   /* r */
  fe_mul(t4, t2, t2);                               /* hh */
  fe_mul(t5, t2, t4);                               /* hhh */
  fe_mul(t4, PX, t4);                               /* v */
  fe_mul(t6, t3, t3); fe_sub(t6, t6, t5); fe_sub(t6, t6, t4); fe_sub(t6, t6, t4);
  fe_sub(t4, t4, t6); fe_mul(t4, t3, t4);
  fe_mul(t5, PY, t5); fe_sub(PY, t4, t5);
  fe_mul(PZ, PZ, t2);
  for (i = 0; i < 16; i++) PX[i] = t6[i];
}

/* k * G, compressed to 33 bytes. Plain double-and-add. */
static void public_key(const u16 *k, u8 *out)
{
  int i, started = 0;
  for (i = 255; i >= 0; i--) {
    if (started) pt_double();
    if ((k[i >> 4] >> (i & 15)) & 1) {
      if (started) pt_add_g();
      else {
        int j;
        for (j = 0; j < 16; j++) { PX[j] = GX[j]; PY[j] = GY[j]; PZ[j] = 0; }
        PZ[0] = 1; started = 1;
      }
    }
  }
  fe_inv(t1, PZ);
  fe_mul(t2, t1, t1);
  fe_mul(PX, PX, t2);
  fe_mul(t2, t1, t2); fe_mul(PY, PY, t2);
  out[0] = (u8)(2 + (PY[0] & 1));
  for (i = 0; i < 16; i++) {
    out[1 + 2*i] = (u8)(PX[15-i] >> 8); out[2 + 2*i] = (u8)PX[15-i];
  }
}

/* ------------------------------------------------------------ Base58Check */
static u8 pay[82], work[82], d1[32], d2[32];
static char b58[120], rev[120];

/* pay[0..77] holds the 78-byte key record; result as text in b58 */
static void base58check(void)
{
  static const char *abc = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
  int i, n = 0, v, q, rem, more;
  sha256(pay, 78, d1); sha256(d1, 32, d2);
  for (i = 0; i < 4; i++) pay[78+i] = d2[i];
  for (i = 0; i < 82; i++) work[i] = pay[i];
  do {
    rem = 0; more = 0;
    for (i = 0; i < 82; i++) {
      v = rem * 256 + work[i]; q = v / 58;
      work[i] = (u8)q; rem = v - q * 58;
      if (q) more = 1;
    }
    rev[n++] = abc[rem];
  } while (more);
  for (i = 0; i < n; i++) b58[i] = rev[n-1-i];
  b58[n] = 0;
}

/* ---------------------------------------------------------------- QR code */
/* One fixed size: version 6 (41 x 41), lowest error correction, byte mode. */
#define QN 41
static u8 gexp[512], glog[256], gen[19];
static u8 qdata[136], qecc[2][18], qstream[172];
static u8 qm[QN][QN];                               /* bit 0 = dark, bit 1 = fixed */
static u8 qt[QN][QN];                               /* the masked trial */
static u8 line[QN];

static void qput(int x, int y, int v) { qm[y][x] = (u8)(2 | (v ? 1 : 0)); }

static void qr_format(int k)
{
  unsigned v = (unsigned)(8 | k) << 10, rem = v;
  int i;
  for (i = 14; i >= 10; i--) if ((rem >> i) & 1) rem ^= 0x537u << (i - 10);
  v = (v | rem) ^ 0x5412u;
  for (i = 0; i < 6; i++) qput(8, i, (v >> i) & 1);
  qput(8, 7, (v >> 6) & 1); qput(8, 8, (v >> 7) & 1); qput(7, 8, (v >> 8) & 1);
  for (i = 9; i < 15; i++) qput(14 - i, 8, (v >> i) & 1);
  for (i = 0; i < 8; i++) qput(QN - 1 - i, 8, (v >> i) & 1);
  for (i = 8; i < 15; i++) qput(8, QN - 15 + i, (v >> i) & 1);
  qput(8, QN - 8, 1);
}

static int qr_mask(int k, int x, int y)
{
  switch (k) {
  case 0: return (x + y) % 2 == 0;
  case 1: return y % 2 == 0;
  case 2: return x % 3 == 0;
  case 3: return (x + y) % 3 == 0;
  case 4: return (x / 3 + y / 2) % 2 == 0;
  case 5: return x * y % 2 + x * y % 3 == 0;
  case 6: return (x * y % 2 + x * y % 3) % 2 == 0;
  }
  return ((x + y) % 2 + x * y % 3) % 2 == 0;
}

static void qr_trial(int k)
{
  int x, y;
  qr_format(k);
  for (y = 0; y < QN; y++)
    for (x = 0; x < QN; x++)
      qt[y][x] = (u8)((qm[y][x] & 1) ^ (!(qm[y][x] & 2) && qr_mask(k, x, y)));
}

static int qr_line_penalty(void)
{
  static const u8 pa[11] = {1,0,1,1,1,0,1,0,0,0,0}, pb[11] = {0,0,0,0,1,0,1,1,1,0,1};
  int i, j, run = 1, score = 0;
  for (i = 1; i <= QN; i++) {                       /* runs of five or more alike */
    if (i < QN && line[i] == line[i-1]) run++;
    else { if (run >= 5) score += run - 2; run = 1; }
  }
  for (i = 0; i < QN - 10; i++) {                   /* shapes that mimic a corner marker */
    for (j = 0; j < 11 && line[i+j] == pa[j]; j++) ;
    if (j == 11) { score += 40; continue; }
    for (j = 0; j < 11 && line[i+j] == pb[j]; j++) ;
    if (j == 11) score += 40;
  }
  return score;
}

static int qr_penalty(void)
{
  int x, y, score = 0, dark = 0;
  long d;
  for (y = 0; y < QN; y++) {
    for (x = 0; x < QN; x++) { line[x] = qt[y][x]; dark += line[x]; }
    score += qr_line_penalty();
  }
  for (x = 0; x < QN; x++) {
    for (y = 0; y < QN; y++) line[y] = qt[y][x];
    score += qr_line_penalty();
  }
  for (y = 0; y < QN - 1; y++)                      /* 2 x 2 blocks alike */
    for (x = 0; x < QN - 1; x++)
      if (qt[y][x] == qt[y][x+1] && qt[y][x] == qt[y+1][x] && qt[y][x] == qt[y+1][x+1])
        score += 3;
  d = (long)dark * 20 - (long)QN * QN * 10;         /* balance of dark and light */
  if (d < 0) d = -d;
  return score + 10 * (int)(d / (QN * QN));
}

static void qr_rs(const u8 *data, u8 *rem)          /* 68 data bytes -> 18 check bytes */
{
  int i, j; u8 f;
  for (j = 0; j < 18; j++) rem[j] = 0;
  for (i = 0; i < 68; i++) {
    f = (u8)(data[i] ^ rem[0]);
    for (j = 0; j < 17; j++) rem[j] = rem[j+1];
    rem[17] = 0;
    if (f) for (j = 0; j < 18; j++) rem[j] ^= gexp[glog[gen[j+1]] + glog[f]];
  }
}

/* text of up to 134 characters -> 41 rows in qt */
static void qr_make(const char *text, int len)
{
  int i, j, x, y, dx, dy, m, right, vert, best = 0, bestscore = -1, score;
  unsigned v;
  /* byte arithmetic for the error-correction step (field 0x11D) */
  v = 1;
  for (i = 0; i < 255; i++) {
    gexp[i] = (u8)v; glog[v] = (u8)i;
    v <<= 1; if (v & 0x100) v ^= 0x11D;
  }
  for (i = 0; i < 255; i++) gexp[i+255] = gexp[i];
  for (i = 0; i < 19; i++) gen[i] = 0;
  gen[0] = 1;
  for (i = 0; i < 18; i++)
    for (j = i + 1; j >= 1; j--)
      gen[j] = (u8)(gen[j] ^ (gen[j-1] ? gexp[glog[gen[j-1]] + i] : 0));
  /* 1. the message as 136 bytes: type, length, text, end mark, padding */
  qdata[0] = (u8)(0x40 | (len >> 4));
  qdata[1] = (u8)((len << 4) | ((u8)text[0] >> 4));
  for (i = 1; i < len; i++) qdata[i+1] = (u8)(((u8)text[i-1] << 4) | ((u8)text[i] >> 4));
  qdata[len+1] = (u8)((u8)text[len-1] << 4);
  for (i = len + 2, j = 0; i < 136; i++, j ^= 1) qdata[i] = (u8)(j ? 0x11 : 0xEC);
  /* 2. two blocks of 68, each with 18 check bytes, interleaved */
  qr_rs(qdata, qecc[0]); qr_rs(qdata + 68, qecc[1]);
  for (i = 0; i < 68; i++) { qstream[2*i] = qdata[i]; qstream[2*i+1] = qdata[68+i]; }
  for (i = 0; i < 18; i++) { qstream[136+2*i] = qecc[0][i]; qstream[137+2*i] = qecc[1][i]; }
  /* 3. the fixed furniture: three corner markers, timing lines, one small marker */
  for (y = 0; y < QN; y++) for (x = 0; x < QN; x++) qm[y][x] = 0;
  for (i = 0; i < QN; i++) { qput(6, i, i % 2 == 0); qput(i, 6, i % 2 == 0); }
  for (i = 0; i < 3; i++) {
    x = (i == 1) ? QN - 4 : 3; y = (i == 2) ? QN - 4 : 3;
    for (dy = -4; dy <= 4; dy++)
      for (dx = -4; dx <= 4; dx++)
        if (x + dx >= 0 && x + dx < QN && y + dy >= 0 && y + dy < QN) {
          m = dx < 0 ? -dx : dx; if ((dy < 0 ? -dy : dy) > m) m = dy < 0 ? -dy : dy;
          qput(x + dx, y + dy, m != 2 && m != 4);
        }
  }
  for (dy = -2; dy <= 2; dy++)
    for (dx = -2; dx <= 2; dx++) {
      m = dx < 0 ? -dx : dx; if ((dy < 0 ? -dy : dy) > m) m = dy < 0 ? -dy : dy;
      qput(34 + dx, 34 + dy, m != 1);
    }
  qr_format(0);                                     /* reserves the squares */
  /* 4. the message, zig-zagging in two-wide columns from the right */
  i = 0;
  for (right = QN - 1; right >= 1; right -= 2) {
    if (right == 6) right = 5;
    for (vert = 0; vert < QN; vert++)
      for (j = 0; j < 2; j++) {
        x = right - j;
        y = ((right + 1) & 2) == 0 ? QN - 1 - vert : vert;
        if (!(qm[y][x] & 2) && i < 172 * 8) {
          qm[y][x] = (u8)((qstream[i >> 3] >> (7 - (i & 7))) & 1);
          i++;
        }
      }
  }
  /* 5. the mask: try all eight, keep the one that scans best */
  for (m = 0; m < 8; m++) {
    qr_trial(m);
    score = qr_penalty();
    if (bestscore < 0 || score < bestscore) { bestscore = score; best = m; }
  }
  qr_trial(best);
}

/* ------------------------------------------------------------ the machine */
static int idx[12];
static u8 ent[16], hash[32], pub[33], fp[4], parent[4], rmd[20], msg[37], I[64];
static u8 text[120];
static u16 key[16], il[16];
static char desc[140];

static int read_number(void)
{
  int c, v = 0;
  do { c = getchar(); } while (c == ' ' || c == '\n' || c == '\r');
  if (c < '0' || c > '9') return -1;
  while (c >= '0' && c <= '9') { v = v * 10 + (c - '0'); c = getchar(); }
  return v;
}

static void hex(const u8 *p, int n, char *out)
{
  static const char *h = "0123456789abcdef";
  int i;
  for (i = 0; i < n; i++) { out[2*i] = h[p[i] >> 4]; out[2*i+1] = h[p[i] & 15]; }
  out[2*n] = 0;
}

static void fingerprint(u8 *out)                    /* of the public key for `key` */
{
  int i;
  public_key(key, pub);
  sha256(pub, 33, hash);
  ripemd160_32(hash, rmd);
  for (i = 0; i < 4; i++) out[i] = rmd[i];
}

int main(void)
{
  static const int path[3] = { 84, 0, 0 };
  static char fphex[9];
  int i, j, n, bits7, len, depth;
  u32 c;

  for (i = 0; i < 11; i++) idx[i] = read_number();
  bits7 = read_number();
  if (bits7 < 0 || bits7 > 127) { printf("input: 11 word numbers then 7 bits as 0-127\n"); return 1; }
  for (i = 0; i < 11; i++) if (idx[i] < 0 || idx[i] > 2047) { printf("bad word number\n"); return 1; }

  /* Job 1: the 12th word. 11 words of 11 bits + 7 bits = 16 bytes; hash once. */
  stage("start");
  for (i = 0; i < 16; i++) ent[i] = 0;
  n = 0;
  for (i = 0; i < 11; i++)
    for (j = 10; j >= 0; j--, n++)
      if ((idx[i] >> j) & 1) ent[n >> 3] |= (u8)(0x80 >> (n & 7));
  for (j = 6; j >= 0; j--, n++)
    if ((bits7 >> j) & 1) ent[n >> 3] |= (u8)(0x80 >> (n & 7));
  sha256(ent, 16, hash);
  idx[11] = (bits7 << 4) | (hash[0] >> 4);
  printf("12th word : %s   switches ", WORDS[idx[11]]);
  for (j = 10; j >= 0; j--) putchar('0' + ((idx[11] >> j) & 1));
  printf("   (list line %d)\n", idx[11] + 1);

  /* Job 2: the lock. Words as text -> 2,048 rounds -> seed -> master key. */
  len = 0;
  for (i = 0; i < 12; i++) {
    if (i) text[len++] = ' ';
    for (j = 0; WORDS[idx[i]][j]; j++) text[len++] = (u8)WORDS[idx[i]][j];
  }
  stage("12th word done; 2048 rounds begin");
  pbkdf2(text, len);
  stage("seed done");
  hmac_key((const u8 *)"Bitcoin seed", 12);
  hmac(T, 64, I);
  for (i = 0; i < 16; i++) key[i] = (u16)(((u16)I[30 - 2*i] << 8) | I[31 - 2*i]);
  fingerprint(fp);
  stage("master fingerprint done");

  for (depth = 1; depth <= 3; depth++) {            /* m / 84' / 0' / 0' */
    if (depth == 3) { fingerprint(parent); stage("parent fingerprint done"); }
    msg[0] = 0;
    for (i = 0; i < 16; i++) { msg[1 + 2*i] = (u8)(key[15-i] >> 8); msg[2 + 2*i] = (u8)key[15-i]; }
    msg[33] = 0x80; msg[34] = 0; msg[35] = 0; msg[36] = (u8)path[depth-1];
    hmac_key(I + 32, 32);
    hmac(msg, 37, I);
    for (i = 0; i < 16; i++) il[i] = (u16)(((u16)I[30 - 2*i] << 8) | I[31 - 2*i]);
    c = addn(key, key, il);                         /* child = (left half + parent) mod order */
    if (c || ge(key, FN)) subn(key, key, FN);
  }
  public_key(key, pub);
  stage("account key done");

  /* the 78-byte record: version, depth, parent, number, chain code, public key */
  pay[4] = 3;
  for (i = 0; i < 4; i++) pay[5+i] = parent[i];
  pay[9] = 0x80; pay[10] = 0; pay[11] = 0; pay[12] = 0;
  for (i = 0; i < 32; i++) pay[13+i] = I[32+i];
  for (i = 0; i < 33; i++) pay[45+i] = pub[i];
  hex(fp, 4, fphex);
  printf("fingerprint: %s\n", fphex);
  pay[0] = 0x04; pay[1] = 0x88; pay[2] = 0xB2; pay[3] = 0x1E;
  base58check();
  printf("xpub       : %s\n", b58);
  pay[0] = 0x04; pay[1] = 0xB2; pay[2] = 0x47; pay[3] = 0x46;
  base58check();
  printf("zpub       : %s\n", b58);
  len = 0;
  desc[len++] = '[';
  for (i = 0; i < 8; i++) desc[len++] = fphex[i];
  for (i = 0; "/84h/0h/0h]"[i]; i++) desc[len++] = "/84h/0h/0h]"[i];
  for (i = 0; b58[i]; i++) desc[len++] = b58[i];
  desc[len] = 0;
  printf("descriptor : %s\n", desc);
  stage("text done");

  /* Job 3: the QR code, one row of 41 bulbs at a time. */
  qr_make(desc, len);
  printf("\nQR code, as the row of 41 bulbs would show it (# = bulb lit)\n");
  for (i = 0; i < QN; i++) {
    printf("  row %2d  ", i + 1);
    for (j = 0; j < QN; j++) putchar(qt[i][j] ? '#' : '.');
    putchar('\n');
  }
  stage("finished");
  return 0;
}
