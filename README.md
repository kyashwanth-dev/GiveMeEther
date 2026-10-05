# GiveMeEther


**Share your PC's internet (even Ethernet-only) with an Android phone over a USB cable. No root, no Wi-Fi adapter, no system-wide install.**

`givemeether` is a lightweight launcher around [Gnirehtet](https://github.com/Genymobile/gnirehtet) (reverse tethering). It downloads the tools it needs into a private folder, waits for your phone, and starts sharing. Plug in, tap Allow, done.

> **Status: v0.1 prototype.** Works on Windows (tested). Linux and macOS are expected to work but are untested. A single-file Rust version with a simple UI is planned.

## How it works

1. A tiny Android app (Gnirehtet's) creates a local VPN on the phone and captures its traffic. No root needed.
2. ADB carries that traffic over the USB cable.
3. A relay on the PC forwards it to the internet through whatever connection the PC has (Ethernet, Wi-Fi, etc.).

## Requirements

- Android phone and a USB cable
- Python 3.8+ on the PC (temporary, until the standalone Rust build exists)
- Internet on the PC (for the first-run download only)

## Quick start

1. **Phone:** enable USB debugging
   *Settings → About phone → tap Build number 7 times → Developer options → USB debugging*
2. **PC:** run
   ```
   python givemeether.py
   ```
3. Plug in the phone, tap **Allow** on the USB debugging prompt, then **OK** on the VPN prompt.
4. The phone is now online through your PC. Press `Ctrl+C` to stop.

On first run, `adb` (Google platform-tools) and Gnirehtet are downloaded to `~/.usb-share`. Nothing is installed system-wide and no admin rights are needed.

## Features

- Automatic download of adb and Gnirehtet on first run
- Plain-language status messages (USB debugging off, tap Allow, phone offline)
- Auto-reconnect when the phone is unplugged and replugged
- Connection health tip: if the link drops 3+ times in 5 minutes, it suggests fixes for weak USB power or a poor cable

## Troubleshooting

| Problem | Fix |
|---|---|
| `adb shell am start ... returned with value 255` | Xiaomi/Redmi/POCO: enable **USB debugging (Security settings)** and **Install via USB**. Oppo/Realme/Vivo: enable **Disable permission monitoring**. Also unlock the phone and turn off any other VPN. |
| Phone not detected | Try another cable or port. Some phones need their vendor's USB driver on Windows. |
| Charging icon flickers | Usually harmless (weak USB 2.0 port power). Use a short, good cable and a USB 3.0 or rear port, and dim the screen. Repeated disconnects point to a bad cable. |
| "Unauthorized" | Tap **Allow** on the phone's USB debugging prompt. |

## Limitations

- **Android only.** iOS does not allow this without jailbreaking.
- USB debugging must be enabled once. Android requires it.
- Slower than native USB tethering, but fine for browsing and streaming.

## Roadmap

- [ ] Standalone Rust binary (no Python, single portable file)
- [ ] Tray / window UI with Start/Stop and guided setup
- [ ] Phone-brand detection with exact setting hints
- [ ] Auto-start on plug-in, custom DNS, speed display
- [ ] CI builds for Windows, Linux, macOS
- [ ] Optional Android TV (USB host) version

## Credits

Built on [Gnirehtet](https://github.com/Genymobile/gnirehtet) by Genymobile (Apache-2.0) and Google's [platform-tools](https://developer.android.com/tools/releases/platform-tools). This project is an independent wrapper and is not affiliated with either.

## License

Apache-2.0
