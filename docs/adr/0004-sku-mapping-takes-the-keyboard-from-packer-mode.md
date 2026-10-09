# ADR 0004 — SKU mapping takes the keyboard from Packer Mode, and gives it back

- **Status:** accepted, 2026-10-09.
- **Deciders:** repo owner
- **Builds on:** ADR 0001 (the scanner invariant), ADR 0002 (every screen on the web tier). ADR 0002 said
  SKU mapping and Worker selection "are never shown while Packer Mode is open", and that a phase which
  changes that needs its own ADR. This is it.

## Decision

*Map SKU* and *Map barcode…* in Packer Mode open the SKU mapping page in place of Packer Mode, with an
order still open. The page is a web page with text fields, so for as long as it shows, the scanner types
into the page and not into the scanner field. These rules make that safe:

1. **The page does one thing.** Opened from Packer Mode it is a **quick map**: one draft row, one add. The
   add writes that one mapping to the file server at once and returns to Packer Mode. Nothing else on the
   page can change a mapping.
2. **A scan can only ever commit as a barcode.** From *Map SKU* the SKU is fixed and the barcode field has
   the focus: a scan is the intended input. From *Map barcode…* the barcode is fixed and the SKU must be a
   line of the open order, so a scan that lands in the SKU field is refused and saves nothing. A barcode
   that is already mapped is replaced only by a click.
3. **A scan with no field is held.** While the page is switching in or out no field has the focus. The
   page buffers keys that reach no field, and hands a complete line (text ended by Enter) to Python as a
   **stray scan**. Stray scans are replayed into Packer Mode, in order, once the scanner field has the
   focus again.
4. **The scanner field has the focus on return**, before anything is replayed.

ADR 0001's invariant is unchanged where it applies: while Packer Mode itself is on screen its web view
never takes the keyboard.

## Context

Before this the two flows were `QInputDialog`s over Packer Mode. They took the keyboard too, as any modal
dialog does, and nothing was said about a scan made while one was open: it typed into the dialog. *Map
SKU* depended on that (the packer scans the barcode into the prompt). *Map barcode…* was a pick list, so a
stray scan could do nothing.

The approved SKU mapping mockup draws one page for all three ways in, with a free-text SKU field. Taken
literally, a stray scan with the focus on SKU would type a barcode, press Enter and save "barcode → another
barcode" for every PC.

Leaving Packer Mode's view hidden for a moment is forced by the tier: a web page cannot be drawn over
another web view by Qt, and the page being left must paint itself blank before it is hidden (ADR 0003), which
takes up to 150 ms on the way back.

## Consequences

- The setup document carries a document-level key listener for stray scans, and `MainWindow` a queue that
  it replays after the switch. A test types real key events through all three cases.
- **Known limit.** A scan cut in half by the switch itself arrives as two fragments: the first is held as
  a stray scan only if its Enter arrives in the page, and the rest is typed into the scanner field. The
  result is a *No match* row the packer can see. It is never a silent mapping.
- A replayed scan is acted on without the packer having watched it happen. Its outcome is in the feedback
  band when Packer Mode returns.
- *Map barcode…* still cannot map to a SKU outside the open order, as before. Doing that is the sidebar's
  SKU mapping.
- The owner checks all of this on Windows with a real scanner before a release: the wedge's timing cannot
  be reproduced offscreen.

## Alternatives considered

**Tell a scan from typing by its speed.** Rejected: the app is used over RDP, where typed keys arrive in
bursts, and Packer Mode itself has never needed the heuristic.

**Keep the scanner in a Qt field above the page.** The page would then have no inputs of its own from
Packer Mode, and the mockup's "From Packer Mode" state could not be built.

**Ignore a stray scan and say so.** Offered to the owner, who chose replay: an ignored scan has to be
made again, and nothing tells the packer which item it was.
