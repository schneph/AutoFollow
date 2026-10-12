# Station Network

A live view of every OpenFollow station discovered on your LAN. Confirm all stations are online and reachable before a show.

Each row is one station – this one or a peer discovered by multicast.

- **Status indicator** – a green dot = online and responding; a red ring = seen previously but not currently reachable. The row takes the same colour, and this station's row is blue.
- **Station name** – the name set under General → Station Settings. This station's row is labelled *(this station)*.
- **Address** – the IP address and web port the station serves on (e.g. `192.0.2.42:80`). Every other station's row opens its web interface in a new window, an offline one at its last known address; the mark after the name says so.

> If no peers appear, check that the other OpenFollow instances are running and on the same network segment. Multicast peer discovery does not cross router hops or VLAN boundaries.

The panel refreshes automatically every 5 seconds. Use **Refresh** for an immediate update – e.g. right after bringing a second station online.

## Freeze outputs

**Freeze outputs**, above the tabs, holds every marker this station controls where it is: PSN, OTP, RTTrPM and the OSC outputs keep sending the frozen positions as live, so lights stay where they are while someone crosses the stage or the camera is moved. Tracking, detection and operator input keep running underneath. **Release** hands each marker straight back to whatever drives it, so a marker that moved while frozen jumps to where it is now.

A freeze can also come from the **Freeze Outputs** key (`f` by default) or gamepad button on the Operator Screen, or from a desk with the `/freeze` OSC cues (see OSC Input). The Operator Screen shows **Outputs frozen** in its top-right corner while it lasts, and this control follows within a second whichever way the freeze was set. A freeze lasts until it is released or the station restarts.
