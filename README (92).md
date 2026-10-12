# KEY

**The key that is cut before the lock. The hand-made half of LOCK.**

KEY is the manual process that makes a Bitcoin seed with dice and records it on a steel plate as dots and numbers. No words are used until the day the key is swept. [LOCK](../README.md) is the machine that takes the finished rows and gives back the checksum and the lock: the one address the key will ever receive to.

Everything in this folder is a draft for a first paper dry run.

## Status

- **Nothing here has been tested by people yet.** The sheets, plates and run sheet are drafts (0.1, 11 October 2026).
- **Practice keys only.** The dry run uses paper and a networked computer. A key made this way must never hold money.
- The steel plates are drawings. No plate has been cut.
- **LOCK's own program still produces the earlier xpub code.** The single-address lock described here exists only in the stand-in so far.
- Sizes assume 3 mm number stamps and 16 mm dice. Both are assumptions.

## How it works

1. **Throw.** Eleven dice, each a fair coin: dots on top is 1, blank on top is 0. One throw gives one row of eleven cells.
2. **Mark.** The dice go into a strip that fixes their order. Each die showing dots becomes one punched dot in that row of the seed plate.
3. **Number.** The same eleven dice point to one cell on the number sheets: 2 orange dice give the sheet, 5 white the row, 4 black the column. Its four-digit number is stamped at the end of the row.
4. **Repeat** for rows 1 to 11. Row 12 takes one throw of the orange and white dice only, which fills its first seven cells.
5. **LOCK** reads the rows from switches and returns the last four cells of row 12 (the checksum).
6. **Check.** Every row is read back from its dots and compared with its stamped number.
7. **The lock.** LOCK then shows the key's address as nineteen rows of lights. They are punched onto a second plate, the lock plate, and the address is written out from it with the address card.

Words appear only at sweep, when the twelve numbers are looked up on the word sheets and typed into a wallet.

## Conventions

| | |
|---|---|
| Dot | ● = 1 = punched. ○ = 0 = left blank |
| Row | 11 cells, grouped 2, 5, 4: sheet, row, column. Read left to right |
| Number | The row read as one binary number, **0000 to 2047, counting from zero**. 0000 is *abandon*, 2047 is *zoo* |
| Word list | The standard BIP39 English list. The numbers are language-neutral, but a wallet is derived from the English words, so a plate's numbers always point into that list |
| Row 12 | First seven cells from the dice, last four from LOCK |
| The lock | One address only: the first native SegWit address, `m/84'/0'/0'/0/0`. It is `bc1q` and 38 characters |
| Lock row | Two characters as 5 + 5 dots, each a number 00 to 31 read with the weights 16 8 4 2 1, and an eleventh dot that makes the row's dot count even |

## Files

| File | What it is |
|---|---|
| `key-dice.pdf` | The eleven dice explained on one page |
| `key-dice-strips.pdf` | Paper strips that hold a throw in order: two row strips and one for row 12. Wordless. Cut out |
| `key-bip39-number-sheets.pdf` | Number sheets A to D: dice to four-digit number, headed in Italian. Used while cutting the key |
| `key-bip39-word-sheets.pdf` | Word sheets A to D, with the number under each word. Used only at sweep |
| `key-seed-plate-design.pdf` | The seed plate: design drawing, two paper plates for the dry run, and a worked example |
| `key-lock-plate-design.pdf` | The lock plate: design drawing, a paper plate for the dry run, and a worked example for the same test key |
| `key-address-card.pdf` | The 32 characters every `bc1` address is written in, each with its number and dots, explained in Italian. The same for every key; nothing on it is secret |
| `key-tablet.pdf` | The workshop tablet: the KEY face and the LOCK face to glue on the two sides of a 12 mm plywood board, worked with flat drawing pins, plus build notes. The faces carry the steps, checks and hand signals in Italian |
| `key-stamp-master.svg` | The "non per uso monetario" sign as one-colour artwork for a stamp maker |
| `key-run-sheet-dry-run.pdf` | Flow A: the steps of the paper dry run, with tick boxes and a log, for a cutter and a checker |
| `key-run-sheet-seedsigner.pdf` | Flow B: a second, independent check of the same practice key on a SeedSigner |
| `key-seedqr.html` | A one-file page that turns the plate's twelve numbers into a SeedQR, the code a SeedSigner scans to load a key. Works offline |
| `key-lock-standin.html` | Stands in for LOCK during the dry run, as a one-file page for a tablet or phone. Dots or numbers in; row 12 and the nineteen lock rows out. Works offline |
| `lock_standin.py` | The same stand-in as a Python script, tied directly to LOCK's reference program |
| `index.html` | A front page linking the two practice tools and the PDFs, for viewing the folder as a web page |

The three pages have an IT / EN switch. They open in Italian on a phone set to Italian, and remember the choice.

## Running the dry run

Print the PDFs. Two people, about an hour and a half (an estimate). Then follow `key-run-sheet-dry-run.pdf`.

The stand-in comes in two forms that give identical answers. The page, `key-lock-standin.html`, opens in any browser and needs nothing installed. The script needs Python 3 and is run from the LOCK folder:

```
python3 KEY/lock_standin.py n1 n2 … n11 bbbbbbb
```

`n1` to `n11` are the numbers of rows 1 to 11, and `bbbbbbb` is the first seven cells of row 12 as 1s and 0s.

To check your setup first, use the worked example on page 3 of the seed plate design:

```
python3 KEY/lock_standin.py 1268 0535 0810 0685 0433 0811 1385 1790 0421 0570 0567 1010010
```

It must answer row 12 = `1313` and the address `bc1qejl9xacvuwn55857qa8jtm6ettgkla6ps0thaq`.

## Checking with a SeedSigner

Flow B repeats the result on a machine that shares no code with LOCK. Open `key-seedqr.html` in a browser, type the plate's twelve numbers, and scan the code with the SeedSigner. Its first receiving address must be the address on the lock plate. The steps are in `key-run-sheet-seedsigner.pdf`.

The code is a Standard SeedQR: the twelve four-digit numbers, counted from 0000, written one after another. That is the plate's number column, so no words are typed. For 604 test keys the page's code is identical, square for square, to the one made by the QR library SeedSigner uses. It has not yet been tried on a SeedSigner.

## Not yet decided or proven

- **Steel.** Grade, thickness, how the grid is put on, and how the plates are fixed or sealed.
- **LOCK's program.** It must be changed to derive and show the single address in place of the xpub code.
- **The address on the outside.** Whether it is also shown as a QR code, made from the written address by any public tool.
- **Row 12 on LOCK.** LOCK's outline enters the seven dice bits on the seven right-hand switches. On the plate they are the seven left-hand cells. One of the two should change so a row is always copied the same way.
- **`reference/keycalc.py`** prints the 12th word's list line counting from 1. Here everything counts from 0.
- **The real ceremony.** This folder covers the paper dry run. The live ceremony, with LOCK and steel, is not written yet.

## Related work

- **LOCK** (this repository): the transparent key calculator.
- **BINARY** (Anonymous Art): eleven sliders for one row, and a dashboard that shows any row's number and word.
- **The Slow Money game:** the same dice and sheets, used with words for family practice.
- **btckeys:** the Keysmith ceremony this process is meant to serve.
