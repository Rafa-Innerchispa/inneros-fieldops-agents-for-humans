# InnerOS Pi01 Solar Bootstrap

Task: `ops_e7058e0ff56d`
Correlation: `inneros-pi01-solar-ha-20260912`
Node: `InnerOs-Pi01` (`192.168.1.97`)
Device model: `Xmart XSI-BB-120-3K-24-MPP`

## Scope

Bootstrap the Raspberry Pi as an InnerOS edge node and determine, from observed hardware evidence, whether the connected solar/UPS USB device can be monitored safely from Home Assistant.

This work is infrastructure bootstrap only. It does not modify inverter, charge-controller or battery settings.

## Verified state

- The Pi is reachable from the InnerOS Intel/control host at `192.168.1.4`.
- `InnerOs-Pi01.localdomain` resolves to `192.168.1.97`.
- SSH key-based access from `192.168.1.4` to the Pi is installed and verified.
- The Pi is running Debian GNU/Linux 13 on a Raspberry Pi kernel.
- The root filesystem is an ext4 filesystem with approximately 223 GiB free during bootstrap.
- The connected USB device is visible as `0665:5161`, reported by `lsusb` as `Cypress Semiconductor USB to Serial`.
- Kernel and udev evidence identify it as a USB HID-class device available through `/dev/bus/usb/001/004`, not a `/dev/ttyUSB*` serial adapter. A hidraw node was announced in early dmesg but is not present in the current `/dev` view.
- NUT is installed and configured in read-only server mode.
- A udev rule grants the `nut` group access to the detected USB/HID device.
- Home Assistant receives live read-only telemetry from the Xmart inverter through PI30/QPIGS.

## Installed/configured files on the Pi

```text
/etc/nut/nut.conf
/etc/nut/ups.conf
/etc/nut/upsd.conf
/etc/nut/upsd.users
/etc/udev/rules.d/60-inneros-solar-nut.rules
```

NUT config backups were written under:

```text
/etc/nut/inneros-backup-20260913T043137Z
```

## Services

```text
nut-server.service: active
nut-driver@inneros_solar.service: inactive; superseded by direct read-only PI30 HID collector
```

The NUT server listens on:

```text
127.0.0.1:3493
192.168.1.97:3493
```

NUT remains available for diagnostics, but live telemetry now uses `/opt/inneros/solar_xmart_mpp_read.py` on the Pi and the user timer `inneros-pi01-solar-ha.timer` on Intel `.4`.

## Home Assistant diagnostic

The existing InnerOS Home Assistant bridge on `192.168.1.4` was used to create/update:

```text
sensor.inneros_pi01_solar_status = online
```

Key attributes include:

```text
host: InnerOs-Pi01
ip: 192.168.1.97
usb_vid_pid: 0665:5161
interface: USB HID via usbfs (/dev/bus/usb/001/004); no tty device
nut_server: 192.168.1.97:3493
nut_driver: nutdrv_qx
protocol: PI30
posted_entities: 9
```

## Current status

Owner identified the inverter as `Xmart XSI-BB-120-3K-24-MPP`. Direct read-only MPP/Voltronic PI30 queries (`QPI`, `QPIGS`) now return telemetry from the detected `0665:5161` HID-class device. The blocker is protocol/driver identification, not LAN reachability, SSH, package installation or Home Assistant connectivity.

Observed live sample:

```text
protocol=PI30
output_power=677 W
battery_voltage=28.8 V
battery_capacity=100 %
load=28 %
```

## Safety decisions

- No inverter/controller write commands were sent.
- No NUT user with `instcmd` or `setvar` privileges was configured.
- No public exposure was added.
- No MQTT broker was added because MQTT on `192.168.1.4:1883` was not available; the existing Home Assistant API bridge was used instead.

## Next driver investigation

Use one of these safe paths before attempting another live driver. Evidence updates: `docs/evidence/inneros_pi01_xmart_probe_20260913.json` and `docs/evidence/inneros_pi01_xmart_live_telemetry_20260913.json`.



1. Identify the exact inverter/controller model from the physical label or vendor app.
2. Capture a read-only HID descriptor/report sample and compare it with known `nutdrv_qx` subdrivers.
3. If the device is actually Modbus/RS485 behind a separate interface, use a supported USB-RS485 adapter and a read-only Modbus poller instead of HID.

Do not mark the solar telemetry collector as live until real voltage/power/state variables are returned and recorded in evidence.
