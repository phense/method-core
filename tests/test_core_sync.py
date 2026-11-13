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
        # macOS temp roots sit below the /var symlink; the lock check refuses symlinked ancestors.
        self.base = Path(self.tmp.name).resolve();self.source = self.base/'source';self.source.mkdir()
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
    def test_umask_dependent_permission_bits_are_not_mode_drift(self):
        # A host umask of 0002 installs 664/775 copies; only the executable bit is recorded by Git.
        self.install()
        (self.target/'shared/platform/codex.md').chmod(0o664);(self.target/'scripts/project-state').chmod(0o775)
        r=self.sync('--check');self.assertEqual(0,r.returncode,r.stdout+r.stderr)
        (self.target/'shared/platform/codex.md').chmod(0o755)
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
    @unittest.skipUnless(os.name == 'posix' and os.geteuid() != 0, 'requires enforced POSIX directory permissions')
    def test_unwritable_unchanged_path_does_not_abort_prior_rollback(self):
        self.install();old=(self.target/'method-core.lock.json').read_bytes()
        self.put('scripts/project-state',b'updated state\n',0o755)
        self.put('shared/platform/codex.md',b'updated adapter\n');self.commit()
        locked=self.target/'shared/platform';locked.chmod(0o555)
        try:
            self.assertNotEqual(0,self.sync('--source-root',str(self.source)).returncode)
        finally: locked.chmod(0o755)
        self.assertEqual(b'#!/usr/bin/env python3\nprint("state")\n',(self.target/'scripts/project-state').read_bytes())
        self.assertEqual(old,(self.target/'method-core.lock.json').read_bytes())
        self.assertEqual(0,self.sync('--check').returncode);self.install()

    def test_keyboard_interrupt_restores_the_installed_version(self):
        self.install();old=(self.target/'method-core.lock.json').read_bytes()
        self.put('scripts/project-state',b'updated state\n',0o755);self.commit()
        spec=importlib.util.spec_from_file_location('core_sync_interrupted',ROOT/'scripts/method_core.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        replace=os.replace;calls=0
        def interrupt_once(src,dst):
            nonlocal calls
            calls+=1
            if calls==2: raise KeyboardInterrupt()
            return replace(src,dst)
        with patch.object(module.os,'replace',side_effect=interrupt_once):
            with self.assertRaises(KeyboardInterrupt): module.synchronize(self.source,self.target)
        self.assertEqual(old,(self.target/'method-core.lock.json').read_bytes())
        self.assertEqual(b'#!/usr/bin/env python3\nprint("state")\n',(self.target/'scripts/project-state').read_bytes())
        self.assertEqual(0,self.sync('--check').returncode)

    def crash_update(self):
        script = """
import importlib.util, os, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('sync_crash',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
replace=m.os.replace
def crash_after_write(src,dst):
    replace(src,dst)
    if Path(dst).name=='project-state': os._exit(23)
m.os.replace=crash_after_write
m.synchronize(Path(sys.argv[2]),Path(sys.argv[3]))
"""
        result=subprocess.run([os.sys.executable,'-c',script,str(ROOT/'scripts/method_core.py'),str(self.source),str(self.target)])
        self.assertEqual(23,result.returncode)

    def test_process_death_can_recover_durable_original_files(self):
        # SIGKILL/powerful termination cannot execute in-memory exception cleanup.
        self.install();old=(self.target/'method-core.lock.json').read_bytes()
        self.put('scripts/project-state',b'updated state\n',0o755);self.commit()
        self.crash_update()
        self.assertNotEqual(0,self.sync('--check').returncode)
        recovery=self.sync('--recover');self.assertEqual(0,recovery.returncode,recovery.stdout+recovery.stderr)
        self.assertEqual(old,(self.target/'method-core.lock.json').read_bytes())
        self.assertEqual(b'#!/usr/bin/env python3\nprint("state")\n',(self.target/'scripts/project-state').read_bytes())
        self.assertEqual(0,self.sync('--check').returncode);self.install()

    @unittest.skipUnless(os.name == 'posix' and os.geteuid() != 0, 'requires enforced POSIX directory permissions')
    def test_blocked_recovery_retains_backups_until_permissions_are_fixed(self):
        self.install();old=(self.target/'method-core.lock.json').read_bytes()
        self.put('scripts/project-state',b'updated state\n',0o755);self.commit()
        self.crash_update()
        locked=self.target/'scripts';locked.chmod(0o555)
        try:
            recovery=self.sync('--recover')
            self.assertNotEqual(0,recovery.returncode)
            self.assertIn('backups retained',recovery.stdout)
            self.assertTrue((self.target/'.method-core-transaction/journal.json').is_file())
        finally: locked.chmod(0o755)
        self.assertEqual(0,self.sync('--recover').returncode)
        self.assertEqual(old,(self.target/'method-core.lock.json').read_bytes())
        self.assertEqual(0,self.sync('--check').returncode)

    def test_an_active_transaction_cannot_be_recovered_or_overwritten(self):
        self.install()
        spec=importlib.util.spec_from_file_location('sync_owner',ROOT/'scripts/method_core.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        path=self.target/'method-core.lock.json';before=path.read_bytes()
        module._begin_transaction(self.target,{path:module._snapshot(path)})
        try:
            self.assertNotEqual(0,self.sync('--recover').returncode)
            self.assertNotEqual(0,self.sync('--source-root',str(self.source)).returncode)
            self.assertEqual(before,path.read_bytes())
        finally: module._recover_transaction(self.target,owner=True)
        self.assertEqual(0,self.sync('--check').returncode)

    def test_recovery_excludes_other_recovery_and_updates_until_finished(self):
        self.install()
        self.put('scripts/project-state',b'updated state\n',0o755);self.commit()
        self.crash_update()
        script = """
import importlib.util, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('paused_recovery',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
replace=m._replace
def pause(path,*args):
    print('recovery locked',flush=True)
    sys.stdin.readline()
    return replace(path,*args)
m._replace=pause
m.recover_transaction(Path(sys.argv[2]))
"""
        child=subprocess.Popen([os.sys.executable,'-c',script,str(ROOT/'scripts/method_core.py'),str(self.target)],
                               stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            self.assertEqual('recovery locked',child.stdout.readline().strip())
            for arguments in [('--recover',),('--source-root',str(self.source))]:
                result=self.sync(*arguments)
                self.assertNotEqual(0,result.returncode)
                self.assertIn('already active',result.stdout)
            child.stdin.write('continue\n');child.stdin.flush()
            output,error=child.communicate(timeout=10)
            self.assertEqual(0,child.returncode,output+error)
        finally:
            if child.poll() is None: child.kill();child.communicate()
        self.assertEqual(0,self.sync('--check').returncode)
        self.install()
        self.assertEqual(b'updated state\n',(self.target/'scripts/project-state').read_bytes())
        self.assertFalse((self.target/'.method-core-transaction').exists())

if __name__=='__main__': unittest.main()
