# GiveMeEther

**Share your PC's internet (even Ethernet-only) with an Android phone over a USB cable. No root, no Wi-Fi adapter, no system-wide install.**

`GiveMeEther` is a lightweight launcher around [Gnirehtet](https://github.com/Genymobile/gnirehtet) (reverse tethering). It downloads the tools it needs into a private folder, waits for your phone, and starts sharing. Plug in, tap Allow, done.

> **Status: v2 (Python + Tkinter).** Core sharing is tested on Windows. The newer features (auto-share, multi-phone, live stats, exe build) still need broader real-device testing. Linux and macOS are expected to work but are untested. A Rust version with everything bundled is planned.

## How it works

1. A tiny Android app (Gnirehtet's) creates a local VPN on the phone and captures its traffic. No root needed.
2. ADB carries that traffic over the USB cable.
3. A relay on the PC forwards it to the internet through whatever connection the PC has (Ethernet, Wi-Fi, etc.).

## Requirements

- Android phone and a USB cable
- Python 3.8+ with Tkinter on the PC, only if you run from source (not needed for the exe)
- Internet on the PC (for the first-run download only)

## Quick start

1. **Phone:** enable USB debugging
   *Settings → About phone → tap Build number 7 times → Developer options → USB debugging*
2. **PC:** run the app (or just double-click [GiveMeEther.exe](https://github.com/kyashwanth-dev/GiveMeEther/releases/latest/download/GiveMeEther.exe), see below)
   ```
   python givemeether.py
   ```
3. Press **Start**, plug in the phone, tap **Allow** on the USB debugging prompt, then **OK** on the VPN prompt.
4. The phone is now online through your PC. Press **Stop** to end sharing.

On first run, `adb` (Google platform-tools) and Gnirehtet are downloaded to `~/.usb-share`. Nothing is installed system-wide and no admin rights are needed.

## Standalone Windows exe

No Python needed on the target PC.

- **Download:** grab [`GiveMeEther.exe`](https://github.com/kyashwanth-dev/GiveMeEther/releases/latest/download/GiveMeEther.exe) from the Releases page, double-click it, plug in your phone.
- **Build it yourself:** on Windows with Python 3.8+ (with Tkinter), in the project folder run:
  ```
  python -m pip install pyinstaller
  python -m PyInstaller --noconfirm --clean --onefile --noconsole --name GiveMeEther givemeether.py
  ```
  The result is `dist\GiveMeEther.exe`. Do not name your script `usb.py`: it clashes with the `pyusb` library and breaks the build.
- **Automatic builds:** pushing a tag like `v2.0.0` runs `.github/workflows/build.yml`, which builds the exe on GitHub and attaches it (with a SHA-256 checksum) to the release.

On first run the exe still downloads adb and Gnirehtet into `~/.usb-share`, so the PC needs internet once. Windows SmartScreen or antivirus may warn about an unsigned, freshly built exe; use "More info > Run anyway" or verify the checksum.

## Prompts you'll see on the phone

| Prompt | What to do |
|---|---|
| **"Allow USB debugging?"** | Tap **Allow**. Tick "Always allow from this computer" so it doesn't ask again. |
| **"Connection request" (VPN)**: *Gnirehtet wants to set up a VPN connection that allows it to monitor network traffic* | Tap **OK**. This is how the app captures the phone's traffic and sends it to the PC. It is a **local** VPN: traffic goes only to your own PC over the USB cable, not to any third-party server. You'll see a key icon in the status bar while sharing. |

The VPN prompt appears the first time you start sharing. If it doesn't appear and the phone stays offline, unlock the screen and make sure no other VPN app is active (Android allows only one VPN at a time).

## Brand-specific permission settings

Some manufacturers add an extra security layer on top of USB debugging. If sharing fails with `returned with value 255`, enable the matching setting in **Developer options**:

| Brand | Setting to enable |
|---|---|
| **Xiaomi / Redmi / POCO** | **USB debugging (Security settings)** and **Install via USB** (these may require a signed-in Mi account and an internet connection to turn on) |
| **Oppo / Realme / Vivo / iQOO** | **Disable permission monitoring** (the exact name varies by ROM version) |
| **Samsung, Pixel, Motorola, others** | Usually nothing extra |

Then unplug and replug the cable and run `givemeether` again.

## Features

Numbers match the project roadmap.

- Automatic download of adb and Gnirehtet on first run
- Plain-language status messages (USB debugging off, tap Allow, phone offline)
- **(2) Window UI:** device table, Start/Stop, Share/Stop selected, and a first-run setup guide
- **(3) Auto-share and auto-reconnect:** phones start sharing when plugged in (can be switched off) and reconnect after a replug
- **(4) Brand detection:** reads the phone's manufacturer and shows the exact setting to enable on Xiaomi, Redmi, POCO, Oppo, Realme and Vivo when sharing fails
- **(6) Live stats per phone:** download and upload speed and data used, read from the phone's VPN interface
- **(8) Multiple phones at once:** one shared relay on the PC, one client per phone
- **(10) Connection health tip:** if a phone drops 3+ times in 5 minutes, the log suggests fixes for weak USB power or a poor cable

## Troubleshooting

| Problem | Fix |
|---|---|
| `adb shell am start ... returned with value 255` | Xiaomi/Redmi/POCO: enable **USB debugging (Security settings)** and **Install via USB**. Oppo/Realme/Vivo: enable **Disable permission monitoring**. Also unlock the phone and turn off any other VPN. |
| Phone not detected | Try another cable or port. Some phones need their vendor's USB driver on Windows. |
| Charging icon flickers | Usually harmless (weak USB 2.0 port power). Use a short, good cable and a USB 3.0 or rear port, and dim the screen. Repeated disconnects point to a bad cable. |
| "Unauthorized" | Tap **Allow** on the phone's USB debugging prompt. |

## Experimental: Android TV / smart panel as the relay

`givemeether-tv-m1/` contains milestone M1 of an Android-to-Android mode: an app for an Android panel (USB host, for example a Teachmint interactive panel) and an app for the phone. They switch the phone into Android Open Accessory mode and run a USB echo test, with no USB debugging needed. It is **not** internet sharing yet; the VPN relay comes in later milestones. See `givemeether-tv-m1/README.md`. The apps are untested.

## Limitations

- **Android only.** iOS does not allow this without jailbreaking.
- USB debugging must be enabled once. Android requires it.
- Slower than native USB tethering, but fine for browsing and streaming.

## Roadmap

- [~] 1. Standalone binary: Windows exe via PyInstaller (done, untested); Rust rewrite with adb and Gnirehtet bundled (planned)
- [x] 2. Window UI with Start/Stop and guided setup (system tray icon still to do)
- [x] 3. Auto-share on plug-in and auto-reconnect
- [x] 4. Phone-brand detection with exact setting hints
- [ ] 5. CI builds and release packages for Windows, Linux, macOS
- [x] 6. Live stats (speed and data used)
- [ ] 7. Custom DNS
- [x] 8. Multiple phones at once
- [ ] 9. Wireless mode (pair once over USB, then no cable)
- [x] 10. Power/cable health tips (shown in the log)
- [ ] 11. Android TV / smart panel mode (M1 echo test written; M2 to M4 pending)
- [ ] 12. Per-app routing and bandwidth limits
- [ ] 13. TV-to-PC mode (depends on the device's USB hardware)

v2 features (2, 3, 4, 6, 8, 10) are implemented but need broader real-device testing.

## Credits

Built on [Gnirehtet](https://github.com/Genymobile/gnirehtet) by Genymobile (Apache-2.0) and Google's [platform-tools](https://developer.android.com/tools/releases/platform-tools). This project is an independent wrapper and is not affiliated with either.

## License

Apache-2.0
