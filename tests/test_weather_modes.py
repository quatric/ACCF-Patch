"""Both weather boot defaults and the bytes embedded in patched DOLs."""
import ctypes
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WEATHER = ROOT / 'tools/weather'
sys.path.insert(0, str(WEATHER))
import apply_weather
from test_weather import Cal, SHIM, cal


class WeatherBootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.libs = {}
        shim = Path(cls.tmp.name) / 'shim.c'
        shim.write_text(SHIM)
        for mode in (0, 1):
            library = Path(cls.tmp.name) / ('weather%d.so' % mode)
            subprocess.check_call(['cc', '-O1', '-shared', '-fPIC', '-I', str(WEATHER),
                                   '-DWEATHER_ENABLE_WITH_B=%d' % mode, str(shim),
                                   str(WEATHER / 'weather.c'), '-o', str(library)])
            lib = ctypes.CDLL(str(library))
            lib.weather_sample_buttons.argtypes = [ctypes.c_uint, ctypes.c_ubyte, ctypes.c_uint]
            lib.weather_type_for_date.argtypes = [ctypes.POINTER(Cal)]
            cls.libs[mode] = lib

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setup_weather(self, mode):
        lib = self.libs[mode]
        lib.weather_reset()
        ctypes.c_int.in_dll(lib, 'g_calls').value = 0
        ctypes.c_int.in_dll(lib, 'g_ret').value = 1
        codes = (ctypes.c_ushort * 8).in_dll(lib, 'g_codes')
        codes[0] = 0
        return lib

    def test_both_boot_defaults(self):
        for mode in (0, 1):
            for core, dev, classic, pressed in [(0, 0, 0, False), (0x400, 0, 0, True),
                                               (0, 2, 0x40, True), (0x800, 0, 0, False),
                                               (0, 1, 0x40, False)]:
                with self.subTest(mode=mode, core=core, dev=dev, classic=classic):
                    lib = self.setup_weather(mode)
                    self.assertEqual(lib.weather_is_disabled(), mode)
                    lib.weather_sample_buttons(core, dev, classic)
                    expected = (1 - mode) if pressed else mode
                    self.assertEqual(lib.weather_is_disabled(), expected)
                    lib.weather_sample_buttons(0, 0, 0)
                    self.assertEqual(lib.weather_is_disabled(), expected)
                    lib.weather_type_for_date(ctypes.byref(cal(2009, 4, 10)))
                    self.assertEqual(ctypes.c_int.in_dll(lib, 'g_calls').value, 0 if expected else 1)
                    lib.weather_sample_buttons(0x400, 2, 0x40)
                    self.assertEqual(lib.weather_is_disabled(), expected)

    def test_title_screen_closes_window(self):
        for mode in (0, 1):
            for module in (0xA5, 0xA6, 0xA2, 1):
                lib = self.setup_weather(mode)
                lib.weather_on_module_link(module)
                lib.weather_sample_buttons(0x400, 2, 0x40)
                self.assertEqual(lib.weather_is_disabled(), mode)


class WeatherApplyTests(unittest.TestCase):
    def test_every_revision_embeds_selected_mode(self):
        data = json.loads((WEATHER / 'weather_patches.json').read_text())
        for rev, entry in data.items():
            start = min(p['address'] for p in entry['patches'])
            end = max(p['address'] + len(bytes.fromhex(p['old'])) for p in entry['patches'])
            raw = bytearray(0x100 + end - start)
            struct.pack_into('>I', raw, 0, 0x100)
            struct.pack_into('>I', raw, 0x48, start)
            struct.pack_into('>I', raw, 0x90, end - start)
            for patch in entry['patches']:
                offset = 0x100 + patch['address'] - start
                old = bytes.fromhex(patch['old'])
                raw[offset:offset + len(old)] = old
            for mode in apply_weather.MODES:
                variant = entry if mode == 'disable_with_b' else entry['enable_with_b']
                with self.subTest(rev=rev, mode=mode):
                    result = apply_weather.apply(raw, rev, mode=mode)
                    dol = apply_weather.patch_dol.Dol(result)
                    offset = dol.v2f(variant['base'])
                    blob = bytes.fromhex(variant['blob'])
                    self.assertEqual(result[offset:offset + len(blob)], blob)
            with self.assertRaises(RuntimeError):
                apply_weather.apply(result, rev, mode='enable_with_b')
        with self.assertRaises(ValueError):
            apply_weather.apply(b'', 'RUUE02', mode='invalid')


if __name__ == '__main__':
    unittest.main()
