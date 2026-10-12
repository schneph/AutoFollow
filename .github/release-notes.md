## What's new

- **Up to three spotlights** in All Performers mode, each following its own performer.
- **Choose whom a spotlight follows from your desk** over OSC.
- **Swap two performers** when the tracker mixes up who is who.
- **Entry zones:** a performer gets the marker of the zone they walk on from.
- **Freeze:** hold every output exactly where it is, then release it.
- **Speed response:** smoothing that loosens while a performer moves fast and stays steady when they stand still.
- **Calibration check:** measures how far floor marks land from where they should over live video.
- **Rehearsal performers:** simulated people walk the stage so you can test your outputs with nobody on it.
- **ChamSys MagicQ:** fills a trigger zone's OSC cues for a MagicQ playback.
- **Projection output:** send a marker's place in a projected image as `[u]` / `[v]` in OSC.
- **Moving lights:** aim fixtures at markers over sACN or Art-Net, or drive them on a grandMA2 over Telnet. These have not been tested on real fixtures or a real console yet, so check them before a show.

## Download

| Your computer | File |
|---|---|
| Mac with Apple Silicon (M1 or later) | `AutoFollow-<version>-arm64.dmg` |
| Windows 10 or 11 (64-bit) | `AutoFollow-<version>-Setup.exe` |

## Install

**Mac:** open the `.dmg` and drag AutoFollow into Applications. The app is not
notarized yet, so the first time, right-click AutoFollow and choose **Open**, or
run `xattr -dr com.apple.quarantine /Applications/AutoFollow.app`.

**Windows:** run the setup file. It is not code-signed yet, so SmartScreen warns
on first run: click **More info**, then **Run anyway**.

AutoFollow is built on [OpenFollow](https://github.com/openfollowapp/openfollow)
and is licensed under the AGPL-3.0.
