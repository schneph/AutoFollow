# Moving Lights

> Moving lights output is experimental. Try it with your fixtures and your console before a show depends on it.

Points moving lights at markers by sending their pan and tilt channels over sACN (E1.31) or Art-Net, or as commands to a grandMA2 over Telnet. Each light follows one marker on this station. The station works out the pan and tilt from where the light hangs, so the beam lands on the marker's position on stage.

## Output

- **Enabled** – start sending. Off sends nothing at all.
- **Protocol** – **sACN**, **Art-Net** or **grandMA2 (Telnet)**.
- **Destination Host** – where to send. Blank sends sACN to each universe's standard multicast group and Art-Net to broadcast. Enter a node's or console's address to send to it alone. For grandMA2 this is the console's (or onPC's) address and is required.
- **Send Rate (FPS)** – packets per second per universe, 1–44. Default: `30`. grandMA2 Telnet sends at most 15 times a second.
- **sACN Priority** – 1–200, default `150`. Set it above your console's priority so a receiver that merges by priority takes the pan and tilt from this station.

### Sharing a universe with the console

Over sACN the station also sends per-address priority (start code `0xDD`) that claims **only** the pan and tilt channels of each light. A node or console that merges per-address priority takes those channels from here and every other channel (intensity, colour, gobo) from the desk. Check your receiver supports per-address priority; one that does not takes the whole universe from the source with the highest priority.

Art-Net has no such priority. Send it to a node that merges (HTP / LTP merge of two sources), or patch the lights' pan and tilt on a universe the console does not send.

## grandMA2 Telnet

For a grandMA2 that cannot merge another source's DMX, the station types each light's pan and tilt into the console's command line instead: `Fixture 101 ; Attribute "Pan" At 12.50 ; Attribute "Tilt" At -40.00`, only when the light has moved.

- **Telnet Port** – default `30000`.
- **User** / **Password** – the console user the station logs in as. Create a user just for this: the values land in that user's programmer, so they never mix with the operator's.
- On the console, allow Telnet login (**Setup → Console → Global Settings → Telnet**).
- Each light needs its **grandMA2 Fixture ID**; a light left at `0` is not sent. Universe, address and channels are not used.
- Values are degrees from the centre of the fixture's travel, as the console shows them. If a light moves the wrong way, use **Invert Pan** / **Invert Tilt** here rather than in the console's patch.

An unreachable console is retried every few seconds, and each light is sent again once it answers.

## Lights

Each light has:

- **Enabled** and **Name**.
- **Follows Marker** – one of this station's controlled markers. Markers from other stations are not followed.
- **grandMA2 Fixture ID** – the light's fixture ID on the console, for grandMA2 Telnet only.
- **Universe** and **Address** – where the fixture is patched. sACN universes are 1–63999, Art-Net 0–32767.
- **Pan Channel** / **Tilt Channel** – the channel numbers within the fixture's mode, counted from 1 (the fixture's first channel is its address).
- **16-bit** – send coarse and fine (the fine channel follows straight after the coarse one). Off sends 8-bit pan and tilt.
- **Pan Range** / **Tilt Range** – the fixture's full travel in degrees, from its manual (often 540 and 270).
- **Invert Pan** / **Invert Tilt** – flip a channel's direction.
- **Mounting** – **Hung** (base up, under a bar) or **On the floor** (base down).
- **X / Y / Z** – where the light is, in metres, in the same stage coordinates as markers (X stage left, Y upstage, Z up).
- **Heading** – the stage bearing the light points at pan centre: 0 is upstage, 90 stage left.
- **Base Pitch** / **Base Roll** – small corrections for a light not hung level.

A marker that stops updating holds its light where it last pointed rather than swinging it to a default.

## Calibrate

Measuring a light's position and heading by hand is rarely accurate enough. Calibrate finds them from where the light points instead:

1. Enter a rough position, the mounting and the travel, and save. Turn the output on.
2. Open **Calibrate**. Drag **Pan** and **Tilt** until the beam sits on a mark; the light follows the sliders instead of its marker.
3. Choose which mark that is (the grid's corners and centre, or **Another point** with its coordinates) and press **Record Mark**.
4. Repeat on at least 4 marks, spread across the stage (the grid corners work well). The error column then shows how well they agree.
5. Press **Solve Position**. The position, heading and base corrections fill in; press **Save** to keep them, then **Hand Back to Marker**.

An error above a degree or two usually means a mark was recorded against the wrong point, or the pan or tilt range is wrong.

## Not yet

- The output does not take an interface pin: it leaves through the interface the routing table picks.
