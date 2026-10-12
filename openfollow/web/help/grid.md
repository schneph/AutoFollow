# Grid

A reference plane drawn over the live video showing where stage coordinates
land in the image. A **visual aid** – it doesn't change tracking; only
calibration sets the maths.

Easiest to set with the **Setup Wizard** (Open Setup Wizard on the Camera &
Grid tab). All distances are in **metres**, relative to the **Reference
Point** – the (0, 0, 0) of your show (see Core Concepts).

## Display

- **Show Grid** – draw or hide the whole grid overlay on the Operator Screen.
  The Origin Marker below has its own toggle, so the origin cross can still show
  when the grid lines are hidden. Display only – it never affects tracking,
  calibration, or any output protocol.

## Dimensions

- **Width** – grid size along X (stage left–right).
- **Depth** – grid size along Y (downstage–upstage).
- **Maximum Height** – vertical extent of the tracking volume above the grid
  plane, used as the denominator for the fractional-height OSC placeholders
  (`[z.frac]` / `[z.frac.inv]`): they divide a marker's height by this value to
  emit a normalised −1…1 fraction. Leave at `0` / empty otherwise – bindings
  that reference those placeholders are skipped while it's unset.
- **Spacing** – distance between grid lines. Visual only; doesn't affect
  calibration.

## Appearance

- **Line Color** – colour of the grid lines.
- **Line Thickness** – line weight in pixels (1–20).
- **Opacity** – `0` fully transparent, `1` fully opaque.

## Offset Position

Use when the Reference Point isn't at the grid centre.

- **X Offset** – shift along X. `0` centres the grid on stage.
- **Y Offset** – shift along Y. Half the depth puts the Reference Point at the
  front (downstage) edge.
- **Z Offset** – height of the grid plane above the Reference Point. `0` sits it
  on the floor; raise it for a stage deck or riser.

## Origin Marker

A small cross at the Reference Point to confirm it lines up with your physical
mark.

- **Show Origin** – turn the marker on or off.
- **Length** – arm length of the cross, in metres.
- **Thickness** – line weight in pixels (1–20).

## Saving & sharing

- **Save** – make the current values durable (Grid applies live but reverts on
  reload until saved).
- **Apply to all stations** – broadcast Camera and Grid to every OpenFollow
  station on the network.
- **Save as template… / Load template…** – store Camera and Grid together as a
  portable file. The Load chooser also lets you **Export** a template as a single
  `.oftemplate` file and **Import** one from another machine.

## Projection Area

Where a projector's image falls on the stage floor, for the `[u]` and `[v]` OSC placeholders that tell a media server such as Resolume where a marker sits in its output (see **OSC Transmitters**).

- **Projection Covers the Grid** – the image fills the grid exactly, top edge upstage and left edge on audience left (stage right). This is the default.
- **Top Left / Top Right / Bottom Right / Bottom Left X and Y** – used when the box above is cleared: the floor position, in stage coordinates, of each corner of the projected image as it appears in the media server's output. Measure where each corner of a full-frame test pattern lands on the floor. A keystoned or rotated image is fine, as long as the four corners go round the image in order.

