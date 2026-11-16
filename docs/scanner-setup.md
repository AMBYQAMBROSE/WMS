# Scanner setup (PDA and USB scanners)

The WMS reads barcodes the way a keyboard types: the scanner "types" the code into the field that has focus and
presses Enter. This is called keyboard wedge mode. No scanner driver or SDK is needed, but the scanner must be set
up as described here. Set up every new device before it goes into use, then check it with the test codes at the end.

Only devices with a hardware scanner are supported. The phone camera is not used for scanning.

## 1. Settings for every scanner

| Setting | Value | Why |
|---|---|---|
| Output mode | Keyboard wedge (keystrokes). On Android PDAs: the vendor's scan app, e.g. DataWedge (Zebra), ScanWedge (Honeywell), Scanner settings (Urovo, Chainway), "keyboard output" | The app reads keystrokes |
| Suffix | Enter (CR, `\r` or `\n`) after every code | Enter ends the scan; without it nothing happens |
| Prefix | None, unless you use symbology identifiers (see 2) | A prefix would become part of the code |
| Symbologies | Code 128, EAN-13 / UPC-A, QR Code, DataMatrix. Also GS1-128 / GS1 DataMatrix / GS1 QR if they are separate options | Item labels, bin labels and documents use Code 128 or QR; supplier cartons use EAN and GS1 codes; stock labels use QR |
| Keyboard layout / character set | US English, or "send as Unicode" | Wrong layouts turn `-` and `(` into other characters |
| Inter-character delay | 0 ms, or the lowest value that loses no characters | Fast but complete scans |
| Scan mode | Single scan per trigger press | Avoids double scans of the same code |

The PDA app keeps the cursor in the scan field and hides the on-screen keyboard. If the soft keyboard pops up on
every scan, turn off "show keyboard on input focus" in the device's keyboard settings, or tap the keyboard button in
the scan field once to hide it.

## 2. GS1 carton codes (batch, expiry, quantity in one scan)

Supplier cartons often carry a GS1-128 barcode or a GS1 DataMatrix / QR code, for example
`(01)06901234567892(17)271231(10)LOT7(30)24`. The PDA reads the item (01), batch (10), expiry date (17) and
quantity (30/37) from it, so receiving, putting away, counting and loading need nothing typed. For that the scanner
must send what separates the fields:

| Setting | Value |
|---|---|
| FNC1 / GS transmission | **On**: send the group separator character GS (ASCII 29, `0x1D`) for FNC1. On Zebra DataWedge: Basic data formatting, then "Send GS" or the advanced rule "Send char 29". On Honeywell: "GS1-128 emulation" or "Transmit FNC1 as GS". |
| Symbology identifier (AIM ID) | Recommended **on** for GS1 symbologies only: the scanner then prefixes `]C1` (GS1-128), `]d2` (GS1 DataMatrix) or `]Q3` (GS1 QR), which the app uses to recognise GS1 codes |

Without GS transmission, codes whose variable fields (batch, quantity) come last still read correctly. A batch
followed by more fields does not, and the PDA shows "Unknown barcode".

Our own **stock labels** (printed from a goods receipt) contain the same information as plain text, e.g.
`(240)SKU-0001(10)L1(17)270531(30)24`. They need no special setting.

## 3. USB scanners on the web console

The web console works with any USB or Bluetooth scanner in keyboard mode with an Enter suffix. Scan into an item,
location or document field; forms are never submitted by a scan's Enter, only with their buttons. A GS1 carton code
scanned into an item field finds its item.

## 4. Check a new device

Print these as a test sheet (System → Labels & printing → test print, or any label printed from Items and
Locations), then on the PDA open **Stock** (home screen) and scan:

1. A bin label: the bin's stock is shown.
2. An item label: where the item is stored is shown.
3. A supplier carton with a GS1 code (or a stock label): the item is found. In Receive, batch, expiry and quantity
   are filled in.
4. A document number from a printed pick list, in the home screen's scan field: the pick list opens.

If a code is not found, scan it into any text field (e.g. the Remark of a document on the web) to see what the
scanner actually sends: missing last characters mean the delay is too short, a missing Enter means no suffix, and
changed punctuation means the wrong keyboard layout.
