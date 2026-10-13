# AutoFollow

**Automatic performer tracking from a webcam, sent straight to your lighting desk and media server.**

AutoFollow watches a stage through an ordinary webcam or video feed, finds every performer in a
calibrated stage space, and sends their positions out live. Moving lights follow people without a
follow-spot operator, and projection content can be mapped onto performers in real time.

AutoFollow runs on Mac (Apple Silicon) and Windows 10 / 11. The current release is
[v0.5.0](https://github.com/schneph/AutoFollow/releases/tag/v0.5.0).

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
| **All Performers** | Gives every person on stage a marker of their own, automatically. When someone leaves and comes back near where they left, they get their old marker back, so their fixtures pick them up again. Up to three spotlights can each follow one chosen performer. |
| **Fully Automatic** | Follows one performer with one marker. |
| **AI Assisted** | An operator steers markers by hand and the detector pulls each one onto the nearest person. |
| **Off** | Markers are driven only by hand (gamepad, mouse, keyboard) or by OSC. |

### Show tools

| Feature | What it does |
| --- | --- |
| **Spotlights** | In All Performers mode, up to three spotlight markers each follow a performer you pick, on the web page, from the Operator Screen or from your desk over OSC (`/follow`). |
| **Swap** | When the tracker mixes two performers up after they cross, swap them so each marker goes back to the right person. |
| **Entry zones** | A performer gets the marker of the zone they walk on from, so each entrance can carry its own patch. |
| **Freeze** | Holds every output exactly where it is (for a camera move or a crossing), then releases it. From the web page, a key, a gamepad button or the `/freeze` OSC cues. |
| **Speed response** | Smoothing that loosens while a performer moves fast and stays steady when they stand still. |
| **Calibration check** | Shows, over live video, how far the floor marks land from where the calibration says they are. |
| **Rehearsal performers** | Up to six simulated people walk the stage, so you can test the desk, zones and outputs with nobody on it. |
| **Trigger zones** | Areas on stage that send OSC cues when people enter and leave, with a preset for ChamSys MagicQ playbacks. |
| **Projection output** | Sends where a marker sits in a projected image as `[u]` / `[v]` in OSC, for media servers such as Resolume. |

### Works with

| Target | How AutoFollow talks to it |
| --- | --- |
| grandMA3 | PSN (PosiStageNet), native tracking input |
| grandMA2 | Moving lights over Telnet (AutoFollow types the pan / tilt commands), or sACN / Art-Net |
| ETC Eos / Ion | OSC (`/eos/chan/<n>/xyz` in metres) |
| Hog 4 / Hog 5 | OSC |
| ChamSys MagicQ | OSC trigger-zone cues for a playback |
| Avolites | Planned (Titan has no direct position input) |
| Disguise | PSN |
| Resolume | OSC (normalised parameters, or `[u]` / `[v]` projection coordinates) |
| Moving lights directly | Pan / tilt over sACN (E1.31) or Art-Net, with a calibrate tool to find where each light hangs |
| Anything else | PSN, OTP, OSC and RTTrPM are all available |

> [!NOTE]
> The moving lights output (sACN, Art-Net and grandMA2 Telnet) has not been tested on real
> fixtures or a real console yet. Try it with your rig before a show depends on it.

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

Download the installer for your computer from the
[latest release](https://github.com/schneph/AutoFollow/releases/latest):

| Your computer | File |
| --- | --- |
| Mac with Apple Silicon (M1 or later) | `AutoFollow-<version>-arm64.dmg` |
| Windows 10 or 11 (64-bit) | `AutoFollow-<version>-Setup.exe` |

### macOS

Open the `.dmg` and drag AutoFollow into Applications. The app is not notarized yet, so the first
time, right-click AutoFollow and choose **Open** (or run
`xattr -dr com.apple.quarantine /Applications/AutoFollow.app`). On first launch macOS asks for
camera access. The web control page opens at `http://localhost:8080`.

### Windows

Run the setup file. It is not code-signed yet, so SmartScreen warns on first run: click
**More info**, then **Run anyway**. The web control page opens in your browser at
`http://localhost:8080`.

### From source

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). The Python package is still named `openfollow`
internally, so commands such as `poetry run openfollow` stay the same.

### First setup

1. Open the web page (`http://<computer-ip>:8080`, or port 80 on a Raspberry Pi install).
2. **Video Source:** pick your camera.
3. **Camera & Grid → Setup Wizard:** enter the stage size and pin the four corners.
4. **Markers:** add one controlled marker per performer you want to track.
5. **Detection:** set Tracking to **All Performers**.
6. **Outputs:** switch on PSN and/or OSC and point them at your desk or media server, or set up
   **Moving Lights** to drive fixtures directly.
7. **Check it:** run the **Calibration Check**, and turn on **Rehearsal performers** to test your
   outputs before anyone is on stage.

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

AutoFollow adds the All Performers tracking mode and its show tools (spotlights, swap, entry
zones, freeze, rehearsal performers), the moving lights output, and Windows support.
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
