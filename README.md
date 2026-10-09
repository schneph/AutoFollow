# AutoFollow

**Automatic performer tracking from a webcam, sent straight to your lighting desk and media server.**

AutoFollow watches a stage through an ordinary webcam or video feed, finds every performer in a
calibrated stage space, and sends their positions out live. Moving lights follow people without a
follow-spot operator, and projection content can be mapped onto performers in real time.

> [!WARNING]
> AutoFollow coordinates the lighting, video and audio of a production. It is not a safety system
> and must not be used for safety-critical applications.

---

## What it does

1. **See the stage.** Point a webcam, USB capture card or network camera (NDI, SRT, RTSP, RTP) at
   the performance space.
2. **Calibrate the space once.** The built-in Setup Wizard maps the camera picture to real stage
   coordinates in metres: mark four corners of the stage and AutoFollow solves the camera.
3. **Track everyone automatically.** On-device person detection (YOLO, run locally with ONNX
   Runtime) finds each body in the picture and works out where they are standing on stage.
4. **Send positions out.** Every tracked performer becomes a marker whose X / Y / Z position is
   streamed to your show-control systems many times a second.

Everything runs offline on the show network. Nothing is sent to the internet.

### Tracking modes

| Mode | What it does |
| --- | --- |
| **All Performers** | Gives every person on stage a marker of their own, automatically. When someone leaves and comes back near where they left, they get their old marker back, so their fixtures pick them up again. |
| **Fully Automatic** | Follows one performer with one marker. |
| **AI Assisted** | An operator steers markers by hand and the detector pulls each one onto the nearest person. |
| **Off** | Markers are driven only by hand (gamepad, mouse, keyboard) or by OSC. |

### Works with

| Target | How AutoFollow talks to it |
| --- | --- |
| grandMA3 | PSN (PosiStageNet), native tracking input |
| grandMA2 | Planned (MA2 has no tracking input, so this needs a Telnet bridge) |
| ETC Eos / Ion | OSC (`/eos/chan/<n>/xyz` in metres) |
| Hog 4 / Hog 5 | OSC |
| Avolites | Planned (Titan has no direct position input) |
| Disguise | PSN |
| Resolume | OSC (normalised parameters) |
| Anything else | PSN, OTP, OSC and RTTrPM are all available |

### Video inputs

| Source | Platform |
| --- | --- |
| USB webcam / capture card | Windows, macOS, Linux |
| NDI®, SRT, RTSP, RTP | All |
| Raspberry Pi Camera | Raspberry Pi |

NDI® is a registered trademark of Vizrt NDI AB and needs the separately installed
[NDI SDK](https://ndi.video/for-developers/ndi-sdk/).

---

## Getting started

### macOS

Download the AutoFollow `.dmg`, open it, and drag AutoFollow into Applications. On first launch
macOS asks for camera access. The web control page opens at `http://localhost:8080`.

### Windows

A Windows installer is in progress and will be published on the [Releases](../../releases) page.

### From source

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). The Python package is still named `openfollow`
internally, so commands such as `poetry run openfollow` stay the same.

### First setup

1. Open the web page (`http://<computer-ip>:8080`, or port 80 on a Raspberry Pi install).
2. **Video Source:** pick your camera.
3. **Camera & Grid → Setup Wizard:** enter the stage size and pin the four corners.
4. **Markers:** add one controlled marker per performer you want to track.
5. **Detection:** set Tracking to **All Performers**.
6. **Outputs:** switch on PSN and/or OSC and point them at your desk or media server.

---

## Security notes

AutoFollow is designed for a trusted show LAN. Before running it on a shared network:

- Set a **web PIN** (General → Network) so only operators can change settings.
- Fill in the **OSC allowed senders** list so only your desks can move markers.
- Peer config sharing only talks to private (LAN) addresses.

---

## Credits

AutoFollow is built on **[OpenFollow](https://github.com/openfollowapp/openfollow)** by Paul
Hermann, Michel Honold and Vinzenz Schultz (<https://openfollow.app>). OpenFollow provides the
video pipeline, camera calibration, person detection and the PSN / OTP / OSC / RTTrPM outputs that
AutoFollow builds on. Many thanks to the OpenFollow team for releasing their work as free software.

AutoFollow adds the All Performers tracking mode and is adding Windows support.
It is an independent project and is not endorsed by or affiliated with the OpenFollow project.
The OpenFollow name, logo and branding belong to their owners and are not part of AutoFollow.

---

## License

AutoFollow is free software under the **GNU Affero General Public License v3.0 or later**, the
same licence as OpenFollow (see [`LICENSE`](LICENSE)).

Copyright (C) 2026 The OpenFollow Project (Paul Hermann, Michel Honold, Vinzenz Schultz) for the
original OpenFollow code, and the AutoFollow contributors for their changes.

Because AutoFollow is used over a network through its web page, AGPL section 13 applies: anyone
using it remotely is entitled to the complete source code, which is this repository.

Third-party components and their licences are listed in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
