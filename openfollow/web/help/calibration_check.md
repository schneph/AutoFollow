# Calibration Check

Shows how far the saved calibration is from the real stage, in centimetres (inches with imperial units), without changing anything.

The page draws the floor marks the Setup Wizard pinned over a live snapshot, where the saved calibration says they are: the four grid corners (**DSL**, **DSR**, **USR**, **USL**) and the centre-stage reference (**REF**, the PSN origin on the floor). The grey ring under each mark stays where the calibration put it.

## Checking

1. Make sure the tape marks the wizard used are still on the floor and visible in the video.
2. Drag each mark onto its real tape mark. With a mark selected, the arrow keys move it one pixel at a time, or ten with **Shift** held.
3. Read the error beside each mark: the distance on the stage between where the calibration puts the mark and where you placed it.

| Error | Means |
|---|---|
| Up to 10 cm (4 in) | Good: a marker lands where the light should |
| 10-30 cm (4-12 in) | Usable, but visibly off at that part of the stage |
| More than 30 cm (12 in), or **Off the stage plane** | Recalibrate |

A large error at one corner only usually means the camera has been knocked or the lens zoomed since calibration. Every mark off by the same amount in the same direction usually means the grid offset is wrong. Either way, open the **Setup Wizard** to recalibrate.

**Refresh Image** takes a new snapshot; **Reset Marks** puts every mark back where the calibration draws it. Nothing on this page is saved.
