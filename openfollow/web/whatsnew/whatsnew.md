v0.5.0
## Follow up to three performers

All Performers mode can now run up to three spotlights, each following its own performer, and a desk can choose whom a spotlight follows over OSC. When the tracker mixes two people up, **Swap** them in the performers panel.

## Freeze, rehearse and check your calibration

**Freeze** holds every output where it is until you release it. **Rehearsal performers** walk simulated people round the stage so you can test outputs with nobody on it, and the **calibration check** measures how far floor marks land from where they should.

## Smoother tracking, entry zones and new outputs

A **speed response** loosens the smoothing while a performer moves fast. **Entry zones** give a performer the marker of the zone they walk on from. Trigger zones can fill their OSC cues for a **ChamSys MagicQ** playback, OSC can send a marker's place in a projected image as `[u]` / `[v]`, and **moving lights** can be aimed at markers over sACN, Art-Net or a grandMA2. The moving lights output has not been tested on real fixtures yet, so check it before a show.

## Check your network pins

USB Ethernet adapters are now named after their MAC (`enx…`). Existing Routing might have moved, check it at **General → Network Interface Assignment**.

## Controller Slots are now stable on restart

Controllers now keep their slot by the USB socket they are plugged into, so one may drive a different marker than before. Check **Input → Controller Slots**.

## Controlled markers are always shown

A marker this station controls now always appears on the Operator Screen and counts in the trigger zones, even if it was hidden before.
