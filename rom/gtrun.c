/* gtrun.c - runs a Gigatron ROM image on the reference CPU model.
 *
 * cpuCycle() is copied unchanged from Docs/gtemu.c in the official
 * gigatron-rom repository (github.com/kervinck/gigatron-rom). One call is
 * one clock tick of the real machine: 6.25 million per second.
 *
 * Commands on standard input, one per line:
 *   R            reset and run until the halt address; prints the tick count
 *   G addr       jump to addr and run until halt; prints the tick count
 *   W addr hex   write bytes into RAM
 *   D addr n     print n bytes of RAM as hex
 *   Z            reset without running;  T n  run n ticks
 *   S hex        set the plug-in module's 16 inputs;  L  print its 24 light outputs
 * usage: gtrun rom.bin halt_address
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { // TTL state that the CPU controls
  uint16_t PC;
  uint8_t IR, D, AC, X, Y, OUT, undef;
} CpuState;

uint8_t ROM[1<<16][2], RAM[1<<15], IN=0xff;

CpuState cpuCycle(const CpuState S)
{
  CpuState T = S; // New state is old state unless something changes

  T.IR = ROM[S.PC][0]; // Instruction Fetch
  T.D  = ROM[S.PC][1];

  int ins = S.IR >> 5;       // Instruction
  int mod = (S.IR >> 2) & 7; // Addressing mode (or condition)
  int bus = S.IR&3;          // Busmode
  int W = (ins == 6);        // Write instruction?
  int J = (ins == 7);        // Jump instruction?

  uint8_t lo=S.D, hi=0, *to=NULL; // Mode Decoder
  int incX=0;
  if (!J)
    switch (mod) {
      #define E(p) (W?0:p) // Disable AC and OUT loading during RAM write
      case 0: to=E(&T.AC);                          break;
      case 1: to=E(&T.AC); lo=S.X;                  break;
      case 2: to=E(&T.AC);         hi=S.Y;          break;
      case 3: to=E(&T.AC); lo=S.X; hi=S.Y;          break;
      case 4: to=  &T.X;                            break;
      case 5: to=  &T.Y;                            break;
      case 6: to=E(&T.OUT);                         break;
      case 7: to=E(&T.OUT); lo=S.X; hi=S.Y; incX=1; break;
    }
  uint16_t addr = (hi << 8) | lo;

  int B = S.undef; // Data Bus
  switch (bus) {
    case 0: B=S.D;                        break;
    case 1: if (!W) B = RAM[addr&0x7fff]; break;
    case 2: B=S.AC;                       break;
    case 3: B=IN;                         break;
  }

  if (W) RAM[addr&0x7fff] = B; // Random Access Memory

  uint8_t ALU; // Arithmetic and Logic Unit
  switch (ins) {
    case 0: ALU =        B; break; // LD
    case 1: ALU = S.AC & B; break; // ANDA
    case 2: ALU = S.AC | B; break; // ORA
    case 3: ALU = S.AC ^ B; break; // XORA
    case 4: ALU = S.AC + B; break; // ADDA
    case 5: ALU = S.AC - B; break; // SUBA
    case 6: ALU = S.AC;     break; // ST
    case 7: ALU = -S.AC;    break; // Bcc/JMP
  }

  if (to) *to = ALU; // Load value into register
  if (incX) T.X = S.X + 1; // Increment X

  T.PC = S.PC + 1; // Next instruction
  if (J) {
    if (mod != 0) { // Conditional branch within page
      int cond = (S.AC>>7) + 2*(S.AC==0);
      if (mod & (1 << cond)) // 74153
        T.PC = (S.PC & 0xff00) | B;
    } else
      T.PC = (S.Y << 8) | B; // Unconditional far jump
  }
  return T;
}
/* ------------------------------------------------ end of gtemu.c code */

static CpuState S;
static unsigned halt;

/* ---- model of the LOCK plug-in module on the game controller port -------------
 * Two lines come out of the Gigatron (bits of the OUT register), one goes in:
 *   PULSE = OUT bit 6    LATCH = OUT bit 7    DATA -> the on-board input register
 * Switches: 16 inputs on two 74HC165. LATCH low loads them; each PULSE rising edge
 *   shifts one bit out on DATA while LATCH is high.
 * Lights: 24 outputs on three 74HC595. Each PULSE rising edge shifts in the level
 *   of LATCH; a LATCH rising edge copies the shift register to the outputs.
 * The Gigatron's input register (U39, a 74HC595 with both clocks on PULSE) takes DATA
 *   on each PULSE rising edge and shows it one pulse later. Check against the real board.
 */
static uint16_t sw_in = 0xffff, sr165 = 0xffff;
static uint64_t sr595 = 0, leds = 0;
static uint8_t in_shift = 0xff;
static unsigned long commits = 0;

static void module_step(uint8_t before, uint8_t after)
{
  int p0 = before & 0x40, p1 = after & 0x40, l0 = before & 0x80, l1 = after & 0x80;
  if (!l1) sr165 = sw_in;
  if (!p0 && p1) {
    /* U39 is a 74HC595 with shift clock and output clock both on PULSE, so the
       value the CPU reads is one pulse behind the shift register. */
    IN = in_shift;
    in_shift = (uint8_t)((in_shift << 1) | ((sr165 >> 15) & 1));
    if (l1) sr165 = (uint16_t)((sr165 << 1) | 1);
    sr595 = ((sr595 << 1) | (l1 ? 1 : 0)) & 0xFFFFFFULL;
  }
  if (!l0 && l1) { leds = sr595; commits++; }
}

static void step(void)
{
  CpuState T = cpuCycle(S);
  if (T.OUT != S.OUT) module_step(S.OUT, T.OUT);
  S = T;
}

static unsigned long long run(void)
{
  unsigned long long t = 0;
  while (S.PC != halt) { step(); t++; }
  return t;
}

int main(int argc, char *argv[])
{
  static char line[4096];
  FILE *fp;
  int i;
  if (argc < 3) { fprintf(stderr, "usage: gtrun rom.bin halt_address\n"); return 1; }
  fp = fopen(argv[1], "rb");
  if (!fp || fread(ROM, 1, sizeof ROM, fp) != sizeof ROM) { fprintf(stderr, "bad ROM file\n"); return 1; }
  fclose(fp);
  halt = (unsigned)strtoul(argv[2], NULL, 0);
  srand(12345);                         /* memory and registers start as rubbish, as on real hardware */
  for (i = 0; i < (int)sizeof RAM; i++) RAM[i] = rand();
  S.IR = rand(); S.D = rand(); S.AC = rand(); S.X = rand(); S.Y = rand(); S.OUT = rand(); S.undef = rand();
  while (fgets(line, sizeof line, stdin)) {
    char *p = line + 1;
    if (line[0] == 'R') {
      S.PC = 0; S = cpuCycle(S); S.PC = 0; S = cpuCycle(S);   /* power-on reset, as in gtemu.c */
      printf("%llu\n", run() + 2);
    } else if (line[0] == 'Z') {          /* reset only */
      S.PC = 0; S = cpuCycle(S); S.PC = 0; S = cpuCycle(S);
      printf("ok\n");
    } else if (line[0] == 'T') {          /* run for a number of ticks (or until halt) */
      unsigned long long n = strtoull(p, NULL, 0), t = 0;
      while (t < n && S.PC != halt) { step(); t++; }
      printf("%llu\n", t);
    } else if (line[0] == 'S') {          /* set the module's 16 inputs (hex; 0 = switch on / button down) */
      sw_in = (uint16_t)strtoul(p, NULL, 16);
      printf("ok\n");
    } else if (line[0] == 'L') {          /* the module's 24 light outputs, and how often they were updated */
      printf("%06llx %lu\n", (unsigned long long)leds, commits);
    } else if (line[0] == 'G') {
      S.PC = (uint16_t)strtoul(p, NULL, 0); S.IR = 0x02; S.D = 0;
      printf("%llu\n", run());
    } else if (line[0] == 'W') {
      unsigned a = (unsigned)strtoul(p, &p, 0), v;
      while (*p == ' ') p++;
      while (sscanf(p, "%2x", &v) == 1) { RAM[a++ & 0x7fff] = (uint8_t)v; p += 2; }
      printf("ok\n");
    } else if (line[0] == 'D') {
      unsigned a = (unsigned)strtoul(p, &p, 0), n = (unsigned)strtoul(p, NULL, 0);
      while (n--) printf("%02x", RAM[a++ & 0x7fff]);
      printf("\n");
    }
    fflush(stdout);
  }
  return 0;
}
