#!/usr/bin/env python3
"""Drag-and-drop SDHC patcher: drop a disc image on the window, done.

Unlike dist.py (which patches pre-dumped reference DOLs for every supported
revision at once, for building the release) this works on one disc the user
actually has: extract it, read its own id/version out of sys/boot.bin, apply
dist.py's site map for that exact revision to its own main.dol, and rebuild.

The rebuilt image replaces the original *in place*, keeping its filename and
folder -- USB loaders key off the `/wbfs/<Title> [ID6]/` layout, so writing a
renamed file next to it can leave the loader unable to launch the title. The
untouched original is kept alongside as `<name>.bak`.

The TMD (and its requested IOS) is left untouched -- only main.dol is patched.
"""
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'gcpad'))
import dist
import patch_dol
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'weather'))
try:
    import apply_weather
except ImportError:                                    # weather stays off rather than stopping the app
    apply_weather = None
from dol import Dol

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAVE_DND = True
except ImportError:                                    # fall back to click-to-browse
    HAVE_DND = False


def find_wit():
    """A wit bundled with this app (PyInstaller build) wins over PATH.

    --add-binary'd files land next to sys._MEIPASS, not next to the
    executable: a plain onedir build puts them in _internal/, and a
    windowed macOS .app puts them in Contents/Frameworks/ instead of
    Contents/MacOS/ alongside the binary.
    """
    name = 'wit.exe' if os.name == 'nt' else 'wit'
    if getattr(sys, 'frozen', False):
        for base in (getattr(sys, '_MEIPASS', None), os.path.dirname(sys.executable)):
            if base:
                bundled = os.path.join(base, name)
                if os.path.isfile(bundled):
                    return bundled
    return shutil.which('wit')


def find_file(root, name):
    for r, _, files in os.walk(root):
        if name in files:
            return os.path.join(r, name)
    return None


def read_disc_id(fst):
    boot = find_file(fst, 'boot.bin')
    if not boot:
        return None
    with open(boot, 'rb') as f:
        header = f.read(8)
    return header[0:6].decode('ascii', 'replace'), header[7]


def key_for(disc_id, disc_ver):
    for key, (label, _src, delta, tid, tver) in dist.TARGETS.items():
        if tid == disc_id and tver == disc_ver:
            return key, label, delta
    return None, None, None


# Korea's discs already support SDHC, so only the controller and weather options apply to them
# (matched on the disc id alone: the version byte in their partition header reads 0 whichever revision this is)
KOREA = {'RUUK01': ('RUUK01v1', 'Tauneuro Nolleogayo: Dongmurui Sup (Korea, Rev 1)'),
         'RUUK02': ('RUUK02', 'Animal Crossing: City Folk Deluxe (Korea)')}


def gcpad_dir():
    if getattr(sys, 'frozen', False):
        return os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)), 'gcpad')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'gcpad')


def run_patch(image_path, log, done, sdhc=True, gc=False, weather=False):
    try:
        wit = find_wit()
        if wit is None:
            raise RuntimeError('wit (Wiimms ISO Tool) not found: not bundled with this '
                                'build and not on PATH')

        fmt = '--iso' if image_path.lower().endswith('.iso') else '--wbfs'

        with tempfile.TemporaryDirectory(prefix='sdhc_patch_') as tmp:
            fst = os.path.join(tmp, 'fst')
            log('extracting %s...' % os.path.basename(image_path))
            r = subprocess.run([wit, 'extract', image_path, '--dest', fst,
                                 '--psel', 'data', '--overwrite', '-q'],
                                capture_output=True, text=True)
            if r.returncode:
                raise RuntimeError('extract failed:\n' + (r.stderr or r.stdout))

            got = read_disc_id(fst)
            if not got:
                raise RuntimeError('could not read sys/boot.bin from the extracted disc')
            disc_id, disc_ver = got
            if not (sdhc or gc or weather):
                raise RuntimeError('nothing selected: tick at least one patch')
            key, label, delta = key_for(disc_id, disc_ver)
            if not key and disc_id in KOREA:
                if sdhc and not (gc or weather):
                    raise RuntimeError('Korean discs already support SDHC cards; tick the controller '
                                       'or weather patch instead.')
                if sdhc:
                    log('Korean disc: SDHC is already supported, skipping that patch')
                    sdhc = False
                key, label = KOREA[disc_id]
            if not key:
                raise RuntimeError(
                    '%s v%d is not a supported target.\n\n'
                    'Supported: %s' % (disc_id, disc_ver,
                                        ', '.join(sorted(t[3] + ' v' + str(t[4])
                                                          for t in dist.TARGETS.values()))))
            log('disc: %s v%d -> %s' % (disc_id, disc_ver, label))

            dol_path = find_file(fst, 'main.dol')
            if not dol_path or os.path.basename(os.path.dirname(dol_path)) != 'sys':
                raise RuntimeError('could not find sys/main.dol in the extracted disc')

            d = Dol(dol_path)
            if sdhc and all(bytes(d.read(va, len(b)) or b'') == b for va, b in dist.rebased_patches(delta)[0]):
                log('SDHC support is already in this disc, skipping that patch')
                sdhc = False
                if not (gc or weather):
                    raise RuntimeError('this disc already has SDHC support; nothing left to add.')
            bad = dist.verify_target(d, delta) if sdhc else None
            if bad:
                raise RuntimeError(
                    'disc does not match the expected site map: %s\n'
                    'Already patched, or an unexpected build of the game -- not patching it.'
                    % ', '.join(bad))

            data = d.data
            patches = []
            if sdhc:
                patches, _cave_end = dist.rebased_patches(delta)
                data = bytearray(d.data)
                for va, blob in patches:
                    fo = d.v2f(va)
                    if fo is None:
                        raise RuntimeError('unmapped patch address 0x%08X' % va)
                    data[fo:fo + len(blob)] = blob
                data = bytes(data)
                log('  added SDHC card support')
            if gc:
                data = patch_dol.apply(data, patch_dol.load(key, root=gcpad_dir()))
                log('  added GameCube controller (port 1) support')
            if weather:
                if apply_weather is None or not apply_weather.available():
                    raise RuntimeError('weather patch data (weather_patches.json) is not available')
                data = apply_weather.apply(data, key)
                log('  added Forecast Channel weather')
            open(dol_path, 'wb').write(data)
            log('  patched main.dol')

            staged = os.path.join(tmp, 'patched.img')
            log('rebuilding...')
            r = subprocess.run([wit, 'copy', fst, '--dest', staged, fmt, '--overwrite', '-q'],
                                capture_output=True, text=True)
            if r.returncode:
                raise RuntimeError('rebuild failed:\n' + (r.stderr or r.stdout))

            # Only touch the user's file once the rebuild has actually succeeded.
            backup = image_path + '.bak'
            if os.path.exists(backup):
                log('  backup already exists, keeping it: %s' % os.path.basename(backup))
            else:
                shutil.copyfile(image_path, backup)
                log('  backed up original -> %s' % os.path.basename(backup))
            shutil.move(staged, image_path)
            log('done: patched in place, %s' % os.path.basename(image_path))
            done(True, image_path)
    except Exception as e:
        log('ERROR: %s' % e)
        done(False, str(e))


BASE = TkinterDnD.Tk if HAVE_DND else tk.Tk


class App(BASE):
    def __init__(self):
        super().__init__()
        self.title('ACCF-Patcher')
        self.geometry('600x500')
        self.msgq = queue.Queue()
        self.busy = False

        hint = ('Drop a .wbfs or .iso here\n\n(or click to choose one)'
                if HAVE_DND else 'Click to choose a .wbfs or .iso')
        self.drop = tk.Label(self, text=hint, relief='ridge', bd=2,
                             padx=10, pady=30, cursor='hand2')
        self.drop.pack(fill='x', padx=10, pady=10)
        self.drop.bind('<Button-1>', lambda e: self.pick())

        if HAVE_DND:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind('<<Drop>>', self.on_drop)

        opts = tk.LabelFrame(self, text='Patches')
        opts.pack(fill='x', padx=10)
        self.sdhc = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text='SDHC card support (cards over 2 GB)',
                       variable=self.sdhc).pack(anchor='w')
        self.gc = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text='GameCube controller in port 1 (as a Classic Controller)',
                       variable=self.gc).pack(anchor='w')

        self.weather = tk.BooleanVar(value=True)
        wcb = tk.Checkbutton(opts, text='Forecast Channel weather (7-day forecast for your location)',
                             variable=self.weather)
        wcb.pack(anchor='w')
        if apply_weather is None or not apply_weather.available():
            wcb.configure(state='disabled')

        tk.Label(self, text='The original is kept alongside as <name>.bak',
                 fg='#666').pack()

        self.log = tk.Text(self, height=14, state='disabled', wrap='word')
        self.log.pack(fill='both', expand=True, padx=10, pady=10)

        self.after(100, self.poll_queue)

    def on_drop(self, event):
        paths = self.tk.splitlist(event.data)      # handles {braced paths with spaces}
        if paths:
            self.start(paths[0])

    def pick(self):
        if self.busy:
            return
        p = filedialog.askopenfilename(
            title='Select disc image',
            filetypes=[('Wii disc image', '*.wbfs *.iso'), ('All files', '*')])
        if p:
            self.start(p)

    def append_log(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def poll_queue(self):
        try:
            while True:
                kind, payload = self.msgq.get_nowait()
                if kind == 'log':
                    self.append_log(payload)
                elif kind == 'done':
                    ok, msg = payload
                    self.busy = False
                    self.drop.configure(state='normal')
                    if ok:
                        messagebox.showinfo('Done', 'Patched in place:\n%s' % msg)
                    else:
                        messagebox.showerror('Patch failed', msg)
        except queue.Empty:
            pass
        self.after(100, self.poll_queue)

    def start(self, image_path):
        if self.busy:
            return
        if not os.path.isfile(image_path):
            messagebox.showerror('Not a file', '%s is not a file.' % image_path)
            return

        self.busy = True
        self.drop.configure(state='disabled')
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')

        threading.Thread(
            target=run_patch,
            args=(image_path,
                  lambda t: self.msgq.put(('log', t)),
                  lambda ok, m: self.msgq.put(('done', (ok, m))),
                  self.sdhc.get(), self.gc.get(), self.weather.get()),
            daemon=True,
        ).start()


if __name__ == '__main__':
    App().mainloop()
