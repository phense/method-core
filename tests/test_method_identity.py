"""Method identity must survive packaging and coexistence in a single host."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from scripts.package_plugin import build_package
ROOT=Path(__file__).resolve().parents[1]

class MethodIdentityTests(unittest.TestCase):
    def test_writing_archive_uses_committed_manifest_identity(self):
        # Hardcoding engineering-method creates an unusable writing release archive.
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'.codex-plugin').mkdir()
            (root/'.codex-plugin/plugin.json').write_text(json.dumps({'name':'writing-method'}))
            (root/'README.md').write_text('writing')
            for args in [('init','-q'),('add','.'),('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture')]:
                subprocess.run(['git','-C',str(root),*args],check=True)
            (root/'.codex-plugin/plugin.json').write_text(json.dumps({'name':'wrong-local-name'}))
            build_package(root,root/'bundle.zip')
            with zipfile.ZipFile(root/'bundle.zip') as archive:
                self.assertIn('writing-method/README.md',archive.namelist())
                self.assertNotIn('wrong-local-name/README.md',archive.namelist())
    def test_both_opencode_loaders_coexist_and_uninstall_is_scoped(self):
        # A fixed loader filename must not overwrite or block the second method.
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);config=base/'config'
            for name in ['engineering-method','writing-method']:
                source=base/name
                for folder in ['integrations/opencode','shared/platform','skills','.codex-plugin']:
                    (source/folder).mkdir(parents=True,exist_ok=True)
                (source/'.codex-plugin/plugin.json').write_text(json.dumps({'name':name}))
                (source/'integrations/opencode/plugin.mjs').write_text('export default async()=>({})')
                (source/'shared/platform/opencode.md').write_text('adapter')
                result=subprocess.run([os.sys.executable,str(ROOT/'scripts/install-opencode'),'--source-root',str(source),'--config-dir',str(config)],capture_output=True,text=True)
                self.assertEqual(0,result.returncode,result.stderr)
            self.assertEqual({'engineering-method.js','writing-method.js'},{p.name for p in (config/'plugins').iterdir()})
            result=subprocess.run([os.sys.executable,str(ROOT/'scripts/install-opencode'),'--source-root',str(base/'writing-method'),'--config-dir',str(config),'--uninstall'],capture_output=True,text=True)
            self.assertEqual(0,result.returncode,result.stderr)
            self.assertEqual({'engineering-method.js'},{p.name for p in (config/'plugins').iterdir()})
