"""Exercise real sync boundaries: modes, overwrite protection and recovery."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]

class CoreSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='method-sync-');self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name);self.source = self.base/'source';self.source.mkdir()
        self.target = self.base/'target';self.target.mkdir()
        subprocess.run(['git','init','-q','-b','main',str(self.source)],check=True)
        for key,value in [('user.name','Sync Test'),('user.email','sync@example.invalid')]: self.git('config',key,value)
        self.put('shared/platform/codex.md',b'adapter v1\n')
        self.put('scripts/project-state',b'#!/usr/bin/env python3\nprint("state")\n',0o755)
        self.manifest(['scripts/project-state','shared/platform/codex.md']);self.commit()
    def put(self,name,data,mode=0o644):
        p=self.source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);p.chmod(mode)
    def manifest(self,exports):
        self.put('method-core.json',json.dumps({'schema_version':1,'name':'method-core','version':'0.1.0','exports':exports}).encode())
    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.source),*args],stderr=subprocess.STDOUT).decode().strip()
    def commit(self):
        self.git('add','.');self.git('commit','-qm','fixture');return self.git('rev-parse','HEAD')
    def sync(self,*args):
        return subprocess.run([os.sys.executable,str(ROOT/'scripts/sync-core'),'--target-root',str(self.target),*args],capture_output=True,text=True)
    def install(self):
        r=self.sync('--source-root',str(self.source));self.assertEqual(0,r.returncode,r.stdout+r.stderr)
    def test_immutable_copy_modes_and_offline_drift_check(self):
        # Dropping execute bits or accepting offline tampering breaks installed commands.
        self.install()
        self.assertEqual(b'adapter v1\n',(self.target/'shared/platform/codex.md').read_bytes())
        self.assertEqual(0o755,(self.target/'scripts/project-state').stat().st_mode&0o777)
        self.assertEqual(0,self.sync('--check').returncode)
        (self.target/'shared/platform/codex.md').write_text('locally edited')
        self.assertNotEqual(0,self.sync('--check').returncode)
        before=(self.target/'method-core.lock.json').read_bytes()
        self.assertNotEqual(0,self.sync('--source-root',str(self.source)).returncode)
        self.assertEqual('locally edited',(self.target/'shared/platform/codex.md').read_text())
        self.assertEqual(before,(self.target/'method-core.lock.json').read_bytes())
    def test_dirty_source_refused_and_explicit_old_revision_can_restore(self):
        self.install();old=self.git('rev-parse','HEAD');self.put('shared/platform/codex.md',b'v2\n')
        self.assertNotEqual(0,self.sync('--source-root',str(self.source)).returncode)
        self.commit();self.install();self.assertEqual(b'v2\n',(self.target/'shared/platform/codex.md').read_bytes())
        r=self.sync('--source-root',str(self.source),'--revision',old)
        self.assertEqual(0,r.returncode,r.stdout+r.stderr)
        self.assertEqual(b'adapter v1\n',(self.target/'shared/platform/codex.md').read_bytes())
    def test_unowned_conflicting_file_and_symlink_are_preserved(self):
        p=self.target/'scripts/project-state';p.parent.mkdir();p.write_text('user-owned')
        self.assertNotEqual(0,self.sync('--source-root',str(self.source)).returncode)
        self.assertEqual('user-owned',p.read_text());self.assertFalse((self.target/'method-core.lock.json').exists())
        p.unlink();outside=self.base/'outside';outside.write_text('keep');p.symlink_to(outside)
        self.assertNotEqual(0,self.sync('--source-root',str(self.source)).returncode)
        self.assertEqual('keep',outside.read_text())
    def test_unsafe_or_duplicate_export_refused_before_writing(self):
        for exports in [['../outside'],['scripts/project-state','scripts/project-state'],['/absolute']]:
            self.manifest(exports);self.commit();self.assertNotEqual(0,self.sync('--source-root',str(self.source)).returncode)
            self.assertEqual([],list(self.target.iterdir()))
    def test_malformed_lock_and_mode_drift_are_not_overwritten(self):
        self.install();(self.target/'scripts/project-state').chmod(0o644)
        self.assertNotEqual(0,self.sync('--check').returncode)
        self.assertNotEqual(0,self.sync('--source-root',str(self.source)).returncode)
        (self.target/'method-core.lock.json').write_text('{"files": []}')
        self.assertNotEqual(0,self.sync('--check').returncode)
    def test_update_adds_and_removes_only_owned_exports(self):
        self.install();self.put('new.txt',b'new');self.manifest(['new.txt','scripts/project-state']);self.commit();self.install()
        self.assertFalse((self.target/'shared/platform/codex.md').exists());self.assertEqual(b'new',(self.target/'new.txt').read_bytes())
        self.assertEqual(0,self.sync('--check').returncode)
    def test_failed_write_restores_old_files_lock_and_permissions(self):
        # A disk failure between managed writes must leave the installed package usable.
        self.install();old=(self.target/'method-core.lock.json').read_bytes()
        self.put('shared/platform/codex.md',b'v2\n');self.commit()
        spec=importlib.util.spec_from_file_location('core_sync_under_test',ROOT/'scripts/method_core.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        replace=os.replace;calls=0
        def fail_once(src,dst):
            nonlocal calls
            calls+=1
            if calls==2: raise OSError('injected write failure')
            return replace(src,dst)
        with patch.object(module.os,'replace',side_effect=fail_once):
            with self.assertRaisesRegex(OSError,'injected'): module.synchronize(self.source,self.target)
        self.assertEqual(old,(self.target/'method-core.lock.json').read_bytes())
        self.assertEqual(b'adapter v1\n',(self.target/'shared/platform/codex.md').read_bytes())
        self.assertEqual(0o755,(self.target/'scripts/project-state').stat().st_mode&0o777)
        self.assertEqual(0,self.sync('--check').returncode);self.install()
if __name__=='__main__': unittest.main()
