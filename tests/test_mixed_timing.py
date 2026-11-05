"""Mixed round deadlines must be exact, reversible and capability-bound."""
import hashlib,json,os,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
from helpers import ROOT
from test_ps_hid import find_vcvars
class MixedTiming(unittest.TestCase):
    def test_manifest_matches_runtime_sites_and_capability(self):
        root=Path(ROOT)
        data=json.loads((root/'tools/eu_mixed_live_immediates.json').read_text())
        sites=sorted((int(s['address'],0),int(s['expected_word'],0)) for s in data['sites'])
        digest=hashlib.sha256(json.dumps(sites,separators=(',',':')).encode('ascii')).hexdigest()
        self.assertIn(digest,(root/'src/netplay/mixed_timing.h').read_text())
        runtime=[tuple(int(v,16) for v in row) for row in re.findall(r'\{ 0x([0-9A-F]+)u, 0x([0-9A-F]+)u, 0x([0-9A-F]+)u \}',(root/'src/netplay/mixed_timing_sites.inc').read_text())]
        self.assertEqual([(a,b) for a,b,c in runtime],sites)
        self.assertTrue(all((a&0xFFFF0000)==(b&0xFFFF0000) for _,a,b in runtime))
        self.assertEqual(len(runtime),9)
    def test_native_reversible_transition(self):
        if os.name!='nt': self.skipTest('clang-cl native fixture requires Windows')
        vc=find_vcvars();cl=shutil.which('clang-cl') or r'C:\Program Files\LLVM\bin\clang-cl.exe'
        if not vc or not os.path.isfile(cl): self.skipTest('native compiler unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            exe=os.path.join(tmp,'timing.exe');src=os.path.join(ROOT,'tests','c','mixed_timing_test.cpp')
            cmd=f'"{vc}" >nul 2>&1 && "{cl}" /nologo /std:c++17 /EHsc /O2 "{src}" /Fe:"{exe}" /Fo:"{tmp}\\timing.obj"'
            built=subprocess.run(f'cmd /s /c "{cmd}"',capture_output=True,text=True,timeout=120)
            self.assertEqual(built.returncode,0,built.stdout+built.stderr)
            ran=subprocess.run([exe],capture_output=True,text=True,timeout=20)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            self.assertIn('PASS exact original/mixed/restored',ran.stdout)
