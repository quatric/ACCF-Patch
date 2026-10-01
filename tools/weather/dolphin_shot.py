#!/usr/bin/env python3
"""Run the game with a real video backend, dump frames, and keep the last one as a PNG.

  dolphin_shot.py <image.wbfs> <build dir> <seconds> <out.png>
"""
import glob, os, shutil, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
os.environ.setdefault("VIDEO", "Metal"); os.environ["FRAMEDUMP"] = "1"
from dolphin_test import start

def main():
    disc, build, secs, out = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
    proc, g, info, blob, sym = start(disc, build)
    user = os.path.join(build, "dolphin_user")
    try:
        g.cmd("?"); g.cont(); time.sleep(secs)
    finally:
        proc.terminate(); proc.wait(10); proc.kill()
    frames = sorted(glob.glob(os.path.join(user, "Dump", "Frames", "**", "*.png"), recursive=True), key=os.path.getmtime)
    print("%d frames dumped" % len(frames))
    if frames:
        base, ext = os.path.splitext(out)
        for k, back in enumerate((2, 150, 300, 450, 600, 900)):
            if back < len(frames):
                shutil.copy(frames[-back], "%s_%d%s" % (base, k, ext))
        print("saved %d sample frames at %s_*%s" % (6, base, ext))
    shutil.rmtree(os.path.join(user, "Dump"), ignore_errors=True)

if __name__ == "__main__":
    main()
