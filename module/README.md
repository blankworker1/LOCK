# The LOCK module

The switches, buttons and lights, on one unit that plugs into the Gigatron's 9-pin controller port. No other port is used.

Status: designed and modelled in the simulator. **Not built.** Build it on a breadboard first. A circuit board comes later, once the breadboard version has run on a kit.

Wiring diagram: [../docs/lock-module.svg](../docs/lock-module.svg).

## The port

| Pin | Line | Direction | Use |
|---|---|---|---|
| 2 | DATA | into the Gigatron | reading switches and buttons |
| 3 | LATCH | out | data for the lights; "load" for the switches |
| 4 | PULSE | out | the clock for everything |
| 6 | +5 V | out | power for the module |
| 8 | 0 V | | ground |

Pins 2, 3 and 4 are from the official Gigatron sources. Pins 6 and 8 are from a contributed adapter board that takes the same controller. **Measure pins 6 and 8 on your board before connecting anything.**

## Parts

| Part | Quantity | Note |
|---|---|---|
| 74HC165 shift register | 2 | reads 16 inputs |
| 74HC595 shift register | 7 | drives 56 outputs, 49 used |
| LED, high efficiency | 49 | 41 for the row, 8 for status |
| Resistor, about 3.3 kΩ | 49 | one per LED, gives about 1 mA |
| Resistor, 10 kΩ | 13 | pull-ups for switches and buttons |
| Capacitor, 100 nF | 9 | one across the power pins of each chip |
| Toggle switch, on/off | 11 | the word |
| Push button | 2 | STORE and NEXT |
| 9-pin D plug and cable | 1 | to the controller port |

## Switches and buttons (two 74HC165)

Each switch or button connects its input to 0 V when closed or pressed. Each input also has a 10 kΩ resistor to +5 V. An unplugged module therefore reads as "everything off".

Chip A is the one whose output goes to the port.

| | Chip A | Chip B |
|---|---|---|
| Input H (pin 6) | word bit 7 | STORE |
| Input G (pin 5) | word bit 6 | NEXT |
| Input F (pin 4) | word bit 5 | +5 V |
| Input E (pin 3) | word bit 4 | +5 V |
| Input D (pin 14) | word bit 3 | +5 V |
| Input C (pin 13) | word bit 2 | word bit 10 |
| Input B (pin 12) | word bit 1 | word bit 9 |
| Input A (pin 11) | word bit 0 | word bit 8 |
| SH/LD (pin 1) | LATCH | LATCH |
| CLK (pin 2) | PULSE | PULSE |
| CLK INH (pin 15) | 0 V | 0 V |
| SER (pin 10) | chip B's QH | +5 V |
| QH (pin 9) | port pin 2, DATA | chip A's SER |
| Power | pin 16 to +5 V, pin 8 to 0 V | same |

Word bit 10 is the leftmost switch and has the value 1024. Word bit 0 is the rightmost and has the value 1. For the coin-flip entry, the seven rightmost switches (bits 6 to 0) are used.

## Lights (seven 74HC595 in a chain)

| Pin | Connect to |
|---|---|
| SER (pin 14) of chip #1 | LATCH |
| SER (pin 14) of chips #2 to #7 | QH' (pin 9) of the chip before |
| SRCLK (pin 11), every chip | PULSE |
| RCLK (pin 12), every chip | LATCH |
| OE (pin 13), every chip | 0 V |
| SRCLR (pin 10), every chip | +5 V |
| Power | pin 16 to +5 V, pin 8 to 0 V |

Each used output goes through its own resistor to an LED, and the LED's other leg to 0 V. Output pins: QA is pin 15, QB to QH are pins 1 to 7.

Which output drives which light:

| Chip | QA | QB | QC | QD | QE | QF | QG | QH |
|---|---|---|---|---|---|---|---|---|
| #1 | count 1 | count 2 | count 4 | count 8 | count 16 | count 32 | mode B | mode A |
| #2 | spare | spare | spare | spare | spare | spare | spare | light 41 |
| #3 | light 40 | light 39 | light 38 | light 37 | light 36 | light 35 | light 34 | light 33 |
| #4 | light 32 | light 31 | light 30 | light 29 | light 28 | light 27 | light 26 | light 25 |
| #5 | light 24 | light 23 | light 22 | light 21 | light 20 | light 19 | light 18 | light 17 |
| #6 | light 16 | light 15 | light 14 | light 13 | light 12 | light 11 | light 10 | light 9 |
| #7 | light 8 | light 7 | light 6 | light 5 | light 4 | light 3 | light 2 | light 1 |

Light 1 is the leftmost of the row of 41. The first 11 lights double as the word display, lined up with the 11 switches.

### Status lights

| Mode A | Mode B | Meaning | The count shows |
|---|---|---|---|
| off | off | entering | entries stored so far |
| off | on | busy | nothing |
| on | off | 12th word | 12 |
| on | on | QR row | the row number, 1 to 41 |

The count is six lights read as a binary number.

## Power

The Gigatron's fuse holds 0.2 A and the board itself uses about 0.1 A. The module must stay well under 0.1 A.

- With 3.3 kΩ resistors each LED takes about 1 mA, so all 49 on is about 50 mA. Use high-efficiency LEDs so that 1 mA is bright enough.
- If brighter lights are wanted, give the module its own 5 V supply and join only the 0 V lines, not the +5 V lines.

## How the program drives it

- **Lights:** the program sets LATCH to each bit in turn and ticks PULSE, 56 times, then raises LATCH once more. That last rise copies all 56 bits to the outputs together.
- **Switches:** LATCH low loads the 16 inputs. LATCH high, then 17 ticks of PULSE, shifts them into the Gigatron: one extra tick first, because the Gigatron's input register shows its value one tick late.
- The program reads the switches and rewrites the lights about 40 times a second.
- A button counts as pressed when seen on two reads in a row, about 50 ms.

## Known limits

- Reading the switches also ticks the light chain, so the lights are rewritten straight after each read. They can show a wrong pattern for about 0.1 ms in every 25 ms. This should not be visible. If it is, one more chip that separates the two functions would remove it.
- The one-tick delay of the input register is allowed for but not yet confirmed on a kit.
- The module model in `rom/gtrun.c` is my reading of the two chip types. The first breadboard run is the real test.

## Later: the circuit board

Not started. Open points for that stage:

- A plain two-layer board with through-hole parts, so every connection can be followed by eye.
- The board is also the face of the artifact: a row of 11 switches under the first 11 of 41 lights.
- Whether to add the extra chip that stops the brief wrong patterns.
- Whether the module gets its own 5 V input.
