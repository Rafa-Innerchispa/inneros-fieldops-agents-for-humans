# InnerOS Pi01 Solar Bootstrap

Task: `ops_e7058e0ff56d`
Correlation: `inneros-pi01-solar-ha-20260912`
Node: `InnerOs-Pi01` (`192.168.1.97`)

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
- Home Assistant receives a diagnostic entity showing the current blocker.

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
nut-driver@inneros_solar.service: inactive/not connected after unsupported-driver probe
```

The NUT server listens on:

```text
127.0.0.1:3493
192.168.1.97:3493
```

The driver is intentionally not treated as healthy because `upsc inneros_solar@localhost` reports `Driver not connected`.

## Home Assistant diagnostic

The existing InnerOS Home Assistant bridge on `192.168.1.4` was used to create/update:

```text
sensor.inneros_pi01_solar_usb_status = driver_not_connected
```

Key attributes include:

```text
host: InnerOs-Pi01
ip: 192.168.1.97
usb_vid_pid: 0665:5161
interface: USB HID via usbfs (/dev/bus/usb/001/004); no tty device
nut_server: 192.168.1.97:3493
nut_driver: nutdrv_qx
driver_status: not_connected
```

## Current blocker

`nutdrv_qx` did not expose telemetry for the detected `0665:5161` HID device. The blocker is protocol/driver identification, not LAN reachability, SSH, package installation or Home Assistant connectivity.

Observed safe failure:

```text
upsc inneros_solar@localhost -> Error: Driver not connected
```

## Safety decisions

- No inverter/controller write commands were sent.
- No NUT user with `instcmd` or `setvar` privileges was configured.
- No public exposure was added.
- No MQTT broker was added because MQTT on `192.168.1.4:1883` was not available; the existing Home Assistant API bridge was used instead.

## Next driver investigation

Use one of these safe paths before attempting another live driver:

1. Identify the exact inverter/controller model from the physical label or vendor app.
2. Capture a read-only HID descriptor/report sample and compare it with known `nutdrv_qx` subdrivers.
3. If the device is actually Modbus/RS485 behind a separate interface, use a supported USB-RS485 adapter and a read-only Modbus poller instead of HID.

Do not mark the solar telemetry collector as live until real voltage/power/state variables are returned and recorded in evidence.
