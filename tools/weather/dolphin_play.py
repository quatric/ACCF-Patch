#!/usr/bin/env python3
"""Open a patched image in a normal Dolphin window, on an isolated user folder (your own NAND/settings untouched).

  dolphin_play.py <image.wbfs> <user dir> [save folder]
Copies in: your controller/input configs, the minimal NAND the game and forecast need (system settings, WiiConnect24 folder,
Forecast Channel data) and, optionally, a raw Wii save folder. The virtual SD card is switched off.
"""
import os, shutil, subprocess, sys

HOME = os.path.expanduser("~/Library/Application Support/Dolphin")

def main():
    image, user = sys.argv[1], sys.argv[2]
    save = sys.argv[3] if len(sys.argv) > 3 else None
    keep = bool(os.environ.get("KEEP")) and os.path.isdir(user)
    if not keep:
        shutil.rmtree(user, ignore_errors=True)
        os.makedirs(os.path.join(user, "Config"))
    if not keep:
        for f in os.listdir(os.path.join(HOME, "Config")):
            if f.endswith(".ini") and f != "Logger.ini":
                shutil.copy(os.path.join(HOME, "Config", f), os.path.join(user, "Config", f))
    ini = os.path.join(user, "Config", "Dolphin.ini")
    text = open(ini).read()
    text = "\n".join("WiiSDCard = False" if ln.startswith("WiiSDCard =") else ln for ln in text.split("\n"))
    if os.environ.get("DEBUG_STUB") and "GDBPort" not in text:
        # a debug connection (port 2159) so the logger can read the game's state while you play; needs the JIT debug checks off
        text = text.replace("[General]\n", "[General]\nGDBPort = 2159\n", 1)
    open(ini, "w").write(text)
    if keep:
        subprocess.check_call(["open", "-n", "-a", "/Applications/Dolphin.app", "--args", "-u", user, "-e", image])
        print("reopened (progress kept)", image)
        return
    for rel in ("shared2/sys", "shared2/wc24", "title/00000001/00000002/data", "title/00010002/48414645"):
        src = os.path.join(HOME, "Wii", rel)
        if os.path.exists(src):
            os.makedirs(os.path.join(user, "Wii", rel), exist_ok=True)
            subprocess.check_call(["rsync", "-a", "--exclude=.DS_Store", src + "/", os.path.join(user, "Wii", rel) + "/"])
    if save:
        dst = os.path.join(user, "Wii", "title", "00010000", "52555545", "data")
        os.makedirs(dst, exist_ok=True)
        for f in os.listdir(save):
            shutil.copy(os.path.join(save, f), os.path.join(dst, f.lower()))
    subprocess.check_call(["open", "-n", "-a", "/Applications/Dolphin.app", "--args", "-u", user, "-e", image])
    print("opened", image)

if __name__ == "__main__":
    main()
