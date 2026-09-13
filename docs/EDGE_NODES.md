# InnerOS Edge Nodes

This inventory lists edge nodes that are allowed to participate in FieldOps and InnerOS physical-site work. It is intentionally small and evidence-driven: a node is listed only after connectivity, host identity and intended role are verified.

## inneros-pi01

| Field | Value |
| --- | --- |
| Hostname | `InnerOs-Pi01` |
| LAN IP | `192.168.1.97` |
| SSH user | `rlopez` |
| Control host | `192.168.1.4` |
| SSH access | Passwordless from the control host using the InnerOS peer-ops key |
| OS | Debian GNU/Linux 13 / Raspberry Pi kernel `6.18.34+rpt-rpi-v8` |
| Primary role | Lab edge node for read-only solar/USB monitoring and future bounded physical-site adapters |
| Evidence | `docs/evidence/inneros_pi01_solar_bootstrap_20260913.json` |

### Allowed capabilities

- Read-only node health and package inspection.
- Read-only USB/HID discovery.
- Read-only solar/UPS telemetry probing.
- Publishing diagnostic state into Home Assistant through the existing InnerOS Home Assistant bridge.
- Future bounded adapters only after an allowlist entry and evidence trail are added.

### Explicitly disallowed without a new approval

- Writing inverter, charge controller or battery settings.
- Running arbitrary shell commands from remote users or untrusted prompts.
- Exposing SSH, NUT or device-management ports directly to the public Internet.
- Adding write-capable NUT users such as `upsmon master` or users with `instcmd`/`setvar` privileges.

### Current solar monitoring status

The Pi detects the connected device as USB HID-class `0665:5161` for owner-reported inverter `Xmart XSI-BB-120-3K-24-MPP` (`Cypress Semiconductor USB to Serial`). NUT is installed and exposes the local NUT server on `127.0.0.1:3493` and `192.168.1.97:3493`, but `nutdrv_qx`, `blazer_usb` and `usbhid-ups` do not currently connect to this HID protocol. Home Assistant receives a diagnostic entity instead of fabricated telemetry:

`sensor.inneros_pi01_solar_usb_status = driver_not_connected`

Until a supported protocol/driver is proven, the correct state is `driver_not_connected`, not `online`.

## Recovery note

After a node reboot, verify the control path with:

```bash
ssh -i ~/.ssh/ralfia_peer_ops_ed25519 -o BatchMode=yes rlopez@192.168.1.97 'hostname; systemctl is-active nut-server.service'
```
