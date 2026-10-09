#!/usr/bin/env python3
"""
givemeether v2 - GUI (Tkinter, standard library only).

Plan items implemented (numbers match the roadmap):
  2. Window UI: device table, Start/Stop, first-run setup guide
  3. Auto-share when a phone is plugged in + auto-reconnect after replug
  4. Phone-brand detection with exact setting hints (Xiaomi/Oppo/Realme/Vivo)
  6. Live stats per phone: download/upload speed and data used
  8. Multiple phones at once (one shared relay, one client per phone)

Keep usb_share.py in the same folder (downloads adb + Gnirehtet on first run).
Run:  python usb_share_gui.py
"""
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import scrolledtext, ttk

import usb_share as core

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # hide console flashes on Windows
GN_PKG = "com.genymobile.gnirehtet"
POLL = 2.0  # seconds between device/stat polls

BRAND_HINTS = {
    ("xiaomi", "redmi", "poco"):
        "Xiaomi/Redmi/POCO: in Developer options enable 'USB debugging (Security settings)' "
        "and 'Install via USB', then replug.",
    ("oppo", "realme", "vivo", "iqoo"):
        "Oppo/Realme/Vivo: in Developer options enable 'Disable permission monitoring', then replug.",
}

GUIDE = """First-time setup (once per phone)

1. On the phone: Settings > About phone > tap "Build number" 7 times.
2. Settings > Developer options > turn on "USB debugging".
   - Xiaomi/Redmi/POCO: also turn on "USB debugging (Security settings)" and "Install via USB".
   - Oppo/Realme/Vivo: also turn on "Disable permission monitoring".
3. Plug the phone in with a good USB DATA cable.
4. Tap ALLOW on the "Allow USB debugging?" prompt (tick "Always allow").
5. Press Start in givemeether. Tap OK on the VPN prompt on the phone.
   (It is a local VPN: traffic goes only to this PC over the cable.)

After that, phones start sharing automatically when plugged in.
Tip: use a short cable and a USB 3.0 / rear port for stable power.
"""


# ---------------- pure helpers (easy to test) ----------------
def parse_tun(text):
    """Return (rx_bytes, tx_bytes) of the first tun* interface in /proc/net/dev, or None."""
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, data = line.split(":", 1)
        if name.strip().startswith("tun"):
            f = data.split()
            if len(f) >= 9:
                return int(f[0]), int(f[8])
    return None


def fmt_bytes(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def fmt_rate(bps):
    return fmt_bytes(bps) + "/s"


def run(cmd, env=None, cwd=None, timeout=30):
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout,
                           env=env, cwd=cwd, creationflags=NO_WINDOW)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:  # timeout, missing file...
        return -1, str(e)


class Device:
    def __init__(self, serial):
        self.serial = serial
        self.name = serial
        self.brand = ""
        self.state = "Detected"
        self.present = True
        self.ready = False      # authorized and info loaded
        self.shared = False     # user/auto wants this phone shared (drives reconnect)
        self.busy = False
        self.last = None        # (time, rx, tx)
        self.down = self.up = 0.0
        self.total_rx = self.total_tx = 0
        self.drops = []         # for core.check_health


class App:
    def __init__(self, root):
        self.root = root
        root.title("givemeether")
        root.geometry("760x560")
        root.minsize(620, 440)

        self.q = queue.Queue()
        self.stop_evt = threading.Event()
        self.thread = None
        self.relay = None
        self.devs = {}
        self.auto_flag = True
        self.master = "Idle"
        self.env = None

        # --- header ---
        self.header = tk.Label(root, text="Idle", font=("Segoe UI", 15, "bold"), fg="#777777")
        self.header.pack(pady=(12, 0))
        self.sub = tk.Label(root, text="Plug in your phone(s), then press Start.")
        self.sub.pack(pady=(0, 6))

        # --- controls ---
        bar = tk.Frame(root)
        bar.pack(pady=4)
        self.btn = tk.Button(bar, text="Start", width=12, height=2, command=self.toggle)
        self.btn.grid(row=0, column=0, padx=4)
        tk.Button(bar, text="Share selected", command=self.share_selected).grid(row=0, column=1, padx=4)
        tk.Button(bar, text="Stop selected", command=self.stop_selected).grid(row=0, column=2, padx=4)
        tk.Button(bar, text="Setup guide", command=self.show_guide).grid(row=0, column=3, padx=4)
        self.auto_var = tk.BooleanVar(value=True)
        tk.Checkbutton(root, text="Auto-share phones when plugged in", variable=self.auto_var,
                       command=lambda: setattr(self, "auto_flag", bool(self.auto_var.get()))).pack()

        # --- device table ---
        cols = ("status", "down", "up", "dtotal", "utotal")
        heads = ("Status", "Down", "Up", "Downloaded", "Uploaded")
        self.tree = ttk.Treeview(root, columns=cols, height=6)
        self.tree.heading("#0", text="Phone")
        self.tree.column("#0", width=190)
        for c, h in zip(cols, heads):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=250 if c == "status" else 90, anchor="w")
        self.tree.pack(fill="x", padx=10, pady=8)

        self.logbox = scrolledtext.ScrolledText(root, height=10, state="disabled", font=("Consolas", 9))
        self.logbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        core.log = self.log  # route core's messages (health tips etc.) into the window
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.pump)
        root.after(500, self.refresh)

        flag = core.HOME / "guide_seen"
        if not flag.exists():
            core.HOME.mkdir(parents=True, exist_ok=True)
            flag.write_text("1")
            root.after(400, self.show_guide)

    # ---------------- UI plumbing ----------------
    def log(self, msg):
        self.q.put(("log", msg))

    def pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.logbox.config(state="normal")
                    self.logbox.insert("end", payload + "\n")
                    if int(self.logbox.index("end-1c").split(".")[0]) > 600:
                        self.logbox.delete("1.0", "100.0")
                    self.logbox.see("end")
                    self.logbox.config(state="disabled")
                elif kind == "btn":
                    self.btn.config(text=payload)
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def refresh(self):
        devs = list(self.devs.values())
        for d in devs:
            vals = (d.state, fmt_rate(d.down) if d.down else "-", fmt_rate(d.up) if d.up else "-",
                    fmt_bytes(d.total_rx), fmt_bytes(d.total_tx))
            if self.tree.exists(d.serial):
                self.tree.item(d.serial, text=d.name, values=vals)
            else:
                self.tree.insert("", "end", iid=d.serial, text=d.name, values=vals)
        sharing = sum(1 for d in devs if d.state == "Sharing")
        if self.master == "Running":
            self.header.config(text=f"Running - {sharing} phone(s) sharing", fg="#1a9b4b" if sharing else "#d98200")
            self.sub.config(text="Plug in a phone to share automatically." if self.auto_flag
                            else "Select a phone and press 'Share selected'.")
        else:
            self.header.config(text=self.master, fg="#777777")
        self.root.after(500, self.refresh)

    def show_guide(self):
        w = tk.Toplevel(self.root)
        w.title("Setup guide")
        w.geometry("560x420")
        t = tk.Text(w, wrap="word", padx=12, pady=12)
        t.insert("1.0", GUIDE)
        t.config(state="disabled")
        t.pack(fill="both", expand=True)

    # ---------------- start / stop ----------------
    def toggle(self):
        if self.thread and self.thread.is_alive():
            self.stop()
        else:
            self.start()

    def start(self):
        self.stop_evt.clear()
        self.q.put(("btn", "Stop"))
        self.thread = threading.Thread(target=self.worker, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_evt.set()
        self.master = "Stopping..."

    def on_close(self, tries=0):
        self.stop()
        if self.thread and self.thread.is_alive() and tries < 40:
            self.root.after(200, lambda: self.on_close(tries + 1))
        else:
            self.root.destroy()

    def selected(self):
        sel = self.tree.selection()
        return self.devs.get(sel[0]) if sel else None

    def share_selected(self):
        d = self.selected()
        if not d or not d.ready or not d.present:
            self.log("Select a connected, authorized phone first.")
        elif self.master != "Running":
            self.log("Press Start first.")
        else:
            threading.Thread(target=self.share, args=(d,), daemon=True).start()

    def stop_selected(self):
        d = self.selected()
        if d:
            d.shared = False
            d.down = d.up = 0.0
            d.last = None
            d.state = "Stopped"
            threading.Thread(target=self.gn, args=("stop", d.serial), daemon=True).start()

    # ---------------- adb / gnirehtet wrappers ----------------
    def adb(self, *args, timeout=20):
        return run([core.ADB, *args], timeout=timeout)

    def gn(self, *args, timeout=60):
        return run([core.GN, *args], env=self.env, cwd=core.GN_DIR, timeout=timeout)

    def adb_list(self):
        rc, out = self.adb("devices")
        res = []
        for line in out.splitlines()[1:]:
            p = line.split()
            if len(p) == 2 and p[1] in ("device", "unauthorized", "offline"):
                res.append((p[0], p[1]))
        return res

    # ---------------- worker ----------------
    def worker(self):
        try:
            self.master = "Preparing tools..."
            core.HOME.mkdir(parents=True, exist_ok=True)
            core.ensure_adb()
            core.ensure_gnirehtet()
            self.env = dict(os.environ, ADB=str(core.ADB))
            self.start_relay()
            self.master = "Running"
            while not self.stop_evt.is_set():
                self.scan_devices()
                self.poll_stats()
                self.ensure_relay()
                self.stop_evt.wait(POLL)
        except Exception as e:
            self.master = "Error"
            self.log(f"Error: {e}")
        finally:
            self.cleanup()

    def start_relay(self):
        self.relay = subprocess.Popen([str(core.GN), "relay"], env=self.env, cwd=core.GN_DIR,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, creationflags=NO_WINDOW)
        threading.Thread(target=self.pipe_reader, args=(self.relay,), daemon=True).start()

    def pipe_reader(self, proc):
        for line in proc.stdout:  # relay is chatty; only surface problems
            if "ERROR" in line or "WARN" in line:
                self.log("relay: " + line.rstrip())

    def ensure_relay(self):
        if self.relay and self.relay.poll() is not None and not self.stop_evt.is_set():
            self.log("Relay stopped unexpectedly; restarting.")
            self.start_relay()

    def scan_devices(self):
        seen = dict(self.adb_list())
        for serial, state in seen.items():
            d = self.devs.get(serial)
            if d is None:
                d = self.devs[serial] = Device(serial)
                self.log(f"Phone detected: {serial}")
            if state == "unauthorized":
                d.present, d.ready = True, False
                d.state = "Tap ALLOW on the phone's USB debugging prompt"
            elif state == "offline":
                d.present, d.ready = True, False
                d.state = "Offline - unplug and replug the cable"
            else:  # authorized
                newly = (not d.ready) or (not d.present)
                d.present = True
                if not d.ready:
                    self.load_info(d)
                    d.ready = True
                if newly and not d.busy:
                    if self.auto_flag or d.shared:
                        threading.Thread(target=self.share, args=(d,), daemon=True).start()
                    else:
                        d.state = "Ready - select and press 'Share selected'"
        for serial, d in self.devs.items():
            if serial not in seen and d.present:
                d.present = d.ready = False
                d.down = d.up = 0.0
                d.last = None
                if d.shared:
                    d.state = "Unplugged - will reconnect when replugged"
                    self.log(f"{d.name} unplugged.")
                    core.check_health(d.drops)
                else:
                    d.state = "Unplugged"

    def load_info(self, d):
        _, brand = self.adb("-s", d.serial, "shell", "getprop", "ro.product.manufacturer")
        _, model = self.adb("-s", d.serial, "shell", "getprop", "ro.product.model")
        d.brand = brand.strip().lower()
        d.name = f"{brand.strip().title()} {model.strip()}".strip() or d.serial

    def brand_hint(self, d):
        for brands, hint in BRAND_HINTS.items():
            if d.brand in brands:
                self.log(f"Hint for {d.name}: {hint}")
                return

    def share(self, d):
        if d.busy:
            return
        d.busy = True
        try:
            d.shared = True
            d.state = "Preparing"
            rc, out = self.adb("-s", d.serial, "shell", "pm", "path", GN_PKG)
            if rc != 0 or "package:" not in out:
                d.state = "Installing app on phone"
                rc, out = self.gn("install", d.serial, timeout=120)
                if rc != 0:
                    return self.fail(d, out)
            self.gn("tunnel", d.serial)
            d.state = "Starting"
            rc, out = self.gn("start", d.serial)
            if rc != 0:
                return self.fail(d, out)
            d.state = "Waiting for VPN - tap OK on the phone (first time only)"
        finally:
            d.busy = False

    def fail(self, d, out):
        d.shared = False
        d.state = "Failed - see log"
        self.log(f"{d.name}: could not start sharing.\n{out[-600:]}")
        self.brand_hint(d)

    def poll_stats(self):
        for d in list(self.devs.values()):
            if not (d.present and d.ready and d.shared) or d.busy:
                continue
            rc, out = self.adb("-s", d.serial, "shell", "cat", "/proc/net/dev")
            res = parse_tun(out) if rc == 0 else None
            now = time.time()
            if res is None:  # VPN not up (yet)
                d.last = None
                d.down = d.up = 0.0
                if d.state == "Sharing":
                    d.state = "Waiting for VPN - tap OK on the phone"
                continue
            rx, tx = res
            if d.last is None:
                d.total_rx += rx
                d.total_tx += tx
            else:
                t0, rx0, tx0 = d.last
                dt = max(now - t0, 0.001)
                drx = rx - rx0 if rx >= rx0 else rx   # counters reset when VPN restarts
                dtx = tx - tx0 if tx >= tx0 else tx
                d.total_rx += drx
                d.total_tx += dtx
                d.down, d.up = drx / dt, dtx / dt
            d.last = (now, rx, tx)
            d.state = "Sharing"

    def cleanup(self):
        for d in list(self.devs.values()):
            if d.present and d.shared:
                self.gn("stop", d.serial, timeout=10)
            d.shared = False
            d.down = d.up = 0.0
            d.last = None
            if d.present:
                d.state = "Stopped"
        if self.relay and self.relay.poll() is None:
            self.relay.terminate()
        if self.master != "Error":
            self.master = "Idle"
        self.q.put(("btn", "Start"))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
