"""Method identity must survive packaging and coexistence in a single host."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
import zipfile
from scripts.package_plugin import build_package
ROOT=Path(__file__).resolve().parents[1]
import engineering_method.issues as issues
from engineering_method.gh import RemoteIssue
from engineering_method.models import BacklogItem, Priority, TaskStatus

class MethodLabelTests(unittest.TestCase):
    """Managed Issues carry the label of the method that owns the backlog."""
    def identity(self, content):
        root=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,root)
        if content is not None:(root/'method.json').write_text(content)
        return root
    def test_label_comes_from_the_bundling_method_identity(self):
        # A hard-coded name labels a Writing Method backlog as engineering-method.
        self.assertEqual('writing-method',issues.method_label(self.identity(json.dumps({'name':'writing-method'}))))
        self.assertEqual('engineering-method',issues.method_label(self.identity(json.dumps({'name':'engineering-method'}))))
    def test_missing_or_unusable_identity_keeps_the_historical_label(self):
        for content in [None,'not json',json.dumps({}),json.dumps({'name':'Bad Name; rm'}),json.dumps({'name':7})]:
            self.assertEqual('engineering-method',issues.method_label(self.identity(content)))
    def test_installed_identity_matches_this_checkout(self):
        manifest=ROOT/'method.json'
        expected=json.loads(manifest.read_text())['name'] if manifest.is_file() else 'engineering-method'
        self.assertEqual(expected,issues.METHOD_LABEL)
        self.assertEqual(issues.METHOD_LABEL,issues.CONTROLLED_LABELS[0][0])
    def test_descriptions_name_the_method(self):
        labels={name:description for name,_,description in issues.controlled_labels('writing-method')}
        self.assertEqual("Managed by Peter's Writing Method.",labels['writing-method'])
        self.assertEqual('Open Writing Method work.',labels['status:open'])
        self.assertNotIn('engineering-method',labels)
    def test_issue_labelled_under_the_historical_name_is_relabelled(self):
        item=BacklogItem(id='WM-001',title='Video',status=TaskStatus.IN_PROGRESS,priority=Priority.P1,parent_id=None,depends_on=(),notes='',updated_at='2026-11-13T00:00:00Z')
        remote=RemoteIssue(id=1,number=1,title='WM-001: Video',body='',state='open',labels=('engineering-method','priority:p1','status:open','custom'),updated_at='2026-11-13T00:00:00Z')
        with unittest.mock.patch.object(issues,'METHOD_LABEL','writing-method'):
            desired=issues._desired_remote_labels(item,remote)
        self.assertEqual(('custom','writing-method','priority:p1','status:in-progress'),desired)

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
            # Resolve first: the installer refuses symlinked parents such as macOS /var.
            base=Path(directory).resolve();config=base/'config'
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
