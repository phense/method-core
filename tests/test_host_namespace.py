"""Shared transcript parsing must respect the selected consumer namespace."""
import json
from pathlib import Path
import tempfile
import unittest
from scripts.run_host_evals import parse_transcript, EvalFailure

class HostNamespaceTests(unittest.TestCase):
    def test_writing_namespace_is_accepted_only_for_its_plugin(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'.codex-plugin').mkdir()
            (root/'.codex-plugin/plugin.json').write_text(json.dumps({'name':'writing-method'}))
            (root/'skills/documentation-pdf').mkdir(parents=True)
            (root/'skills/documentation-pdf/SKILL.md').write_text('PDF instructions')
            events=[{'type':'assistant','message':{'content':[{'type':'tool_use','id':'s1','name':'Skill','input':{'skill':'writing-method:documentation-pdf'}}]}},{'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':'s1','content':'PDF instructions'}]}},{'type':'result','subtype':'success','is_error':False,'structured_output':{'primary':'writing-method:documentation-pdf','supporting':[]}}]
            transcript='\n'.join(map(json.dumps,events))
            parsed=parse_transcript('claude',transcript,plugin=root)
            self.assertEqual('documentation-pdf',parsed['decision']['primary'])
            with self.assertRaises(EvalFailure): parse_transcript('claude',transcript.replace('writing-method:','foreign-method:'),plugin=root)
