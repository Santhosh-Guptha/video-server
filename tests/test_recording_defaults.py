import ast
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import yaml


class RecordingDefaultsTests(unittest.TestCase):
    def test_startup_preserves_shared_ingest_overrides(self):
        source = Path(__file__).resolve().parents[1] / 'backend/app/main.py'
        tree = ast.parse(source.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'configure_mediamtx_paths_dynamically')
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'mediamtx.yml'
            helper = {'source': 'rtsp://camera/live', 'record': False, 'runOnRecordSegmentComplete': ''}
            config.write_text(yaml.safe_dump({'pathDefaults': {'record': True}, 'paths': {'_ingest_test': helper}}))
            for node in ast.walk(function):
                if isinstance(node, ast.Constant) and node.value == '/opt/mediamtx/mediamtx.yml':
                    node.value = str(config)
            namespace = {'settings': SimpleNamespace(recording_dir=directory, segment_time_seconds=60), '__file__': str(source)}
            exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
            namespace['configure_mediamtx_paths_dynamically']()
            result = yaml.safe_load(config.read_text())
            self.assertEqual(result['paths']['_ingest_test'], helper)
            self.assertEqual(result['pathDefaults']['recordSegmentDuration'], '60s')
            before = config.read_bytes()
            namespace['configure_mediamtx_paths_dynamically']()
            self.assertEqual(config.read_bytes(), before)
