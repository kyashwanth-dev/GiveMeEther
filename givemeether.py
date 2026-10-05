#!/usr/bin/env python3
"""
usb-share v0.1 (prototype)
Share a PC's internet (e.g. Ethernet-only) with an Android phone over USB.

Uses only the Python standard library. On first run it downloads:
  - Google platform-tools (adb)
  - Gnirehtet (Apache-2.0, by Genymobile) relay + Android APK
into ~/.usb-share. Nothing is installed system-wide, no admin rights needed.

Usage:  python usb_share.py
Stop:   Ctrl+C
"""
import io
import json
import os
import platform
import stat
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

HOME = Path.home() / ".usb-share"
SYSTEM = platform.system()  # Windows / Linux / Darwin
EXE = ".exe" if SYSTEM == "Windows" else ""

PT_KEY = {"Windows": "windows", "Linux": "linux", "Darwin": "darwin"}.get(SYSTEM)
GN_KEY = {"Windows": "win64", "Linux": "linux64", "Darwin": "macos"}.get(SYSTEM)

ADB = HOME / "platform-tools" / f"adb{EXE}"
GN_DIR = HOME / "gnirehtet"
GN = GN_DIR / f"gnirehtet{EXE}"


def log(msg):
    print(f"[usb-share] {msg}", flush=True)


def download_zip(url, dest):
    log(f"Downloading {url.split('/')[-1]} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "usb-share"})
    data = urllib.request.urlopen(req, timeout=120).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(dest)


def make_executable(path):
    if SYSTEM != "Windows" and path.exists():
        path.chmod(path.stat().st_mode | stat.S_IEXEC)


def ensure_adb():
    if ADB.exists():
        return
    url = f"https://dl.google.com/android/repository/platform-tools-latest-{PT_KEY}.zip"
    download_zip(url, HOME)
    make_executable(ADB)


def ensure_gnirehtet():
    if GN.exists():
        return
    log("Looking up latest Gnirehtet release ...")
    req = urllib.request.Request(
        "https://api.github.com/repos/Genymobile/gnirehtet/releases/latest",
        headers={"User-Agent": "usb-share"},
    )
    release = json.load(urllib.request.urlopen(req, timeout=30))
    asset = next(
        (a for a in release["assets"]
         if "rust" in a["name"] and GN_KEY in a["name"] and a["name"].endswith(".zip")),
        None,
    )
    if not asset:
        sys.exit(
            f"No prebuilt Gnirehtet for {SYSTEM}. Build it from source "
            "(github.com/Genymobile/gnirehtet) and place the binary + .apk in "
            f"{GN_DIR}"
        )
    tmp = HOME / "_gn_tmp"
    download_zip(asset["browser_download_url"], tmp)
    # zip contains a single top-level folder; flatten it into GN_DIR
    inner = next(p for p in tmp.iterdir() if p.is_dir())
    GN_DIR.mkdir(parents=True, exist_ok=True)
    for f in inner.iterdir():
        f.replace(GN_DIR / f.name)
    make_executable(GN)


def adb_devices():
    out = subprocess.run([str(ADB), "devices"], capture_output=True, text=True).stdout
    devices = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) == 2:
            devices.append(parts)  # [serial, state]
    return devices


def wait_for_phone():
    shown = None
    while True:
        devs = adb_devices()
        if any(state == "device" for _, state in devs):
            return
        if any(state == "unauthorized" for _, state in devs):
            msg = "Phone found. Tap ALLOW on the 'Allow USB debugging?' prompt."
        elif any(state == "offline" for _, state in devs):
            msg = "Phone is offline. Unplug and replug the cable."
        else:
            msg = ("Waiting for phone ... Enable USB debugging "
                   "(Settings > About phone > tap Build number 7x > Developer options).")
        if msg != shown:
            log(msg)
            shown = msg
        time.sleep(2)


def check_health(drops, window=300, limit=3):
    """If the relay restarts `limit`+ times within `window` seconds,
    the USB link is unstable: show a power/cable troubleshooting tip."""
    now = time.time()
    drops.append(now)
    drops[:] = [t for t in drops if now - t <= window]
    if len(drops) >= limit:
        log("-" * 60)
        log(f"Connection dropped {len(drops)} times in the last {window // 60} minutes.")
        log("This usually means weak USB power or a poor cable/port. Try:")
        log("  1. A short, good-quality cable (ideally the one from the phone).")
        log("  2. A USB 3.0 (blue) or rear motherboard port, not a front panel/hub.")
        log("  3. Turning the phone screen off or dimming it while sharing.")
        log("  4. Developer options > Default USB configuration > Charging only.")
        log("A flickering charge icon alone is harmless; repeated drops are not.")
        log("-" * 60)
        drops.clear()


def main():
    if not PT_KEY:
        sys.exit(f"Unsupported OS: {SYSTEM}")
    HOME.mkdir(parents=True, exist_ok=True)
    ensure_adb()
    ensure_gnirehtet()

    env = dict(os.environ, ADB=str(ADB))
    log("Ready. Plug in your phone via USB.")
    drops = []  # timestamps of recent relay restarts
    try:
        while True:
            wait_for_phone()
            log("Phone connected. Starting internet sharing "
                "(accept the VPN prompt on the phone the first time).")
            proc = subprocess.run([str(GN), "run"], env=env, cwd=GN_DIR)
            log(f"Relay stopped (exit {proc.returncode}). Reconnecting in 3s ... Ctrl+C to quit.")
            check_health(drops)
            time.sleep(3)
    except KeyboardInterrupt:
        log("Bye.")


if __name__ == "__main__":
    main()
