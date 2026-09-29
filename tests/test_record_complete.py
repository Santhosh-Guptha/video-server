import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app import record_complete


class RecordingHookTests(unittest.TestCase):
    def test_forwards_original_segment_without_probing_or_renaming(self):
        with tempfile.TemporaryDirectory() as directory:
            segment = Path(directory) / '20260929_090000_live.mp4'
            segment.write_bytes(b'original recording bytes')
            response = MagicMock()
            response.__enter__.return_value.getcode.return_value = 200
            response.__enter__.return_value.read.return_value = b'{"status":"ok"}'
            with patch.object(sys, 'argv', ['record_complete', 'camera_MAIN', str(segment)]), \
                 patch('subprocess.run') as probe, \
                 patch('os.rename') as rename, \
                 patch.object(record_complete.urllib.request, 'urlopen', return_value=response) as post:
                record_complete.main()
                request = post.call_args.args[0]
                self.assertEqual(json.loads(request.data), {
                    'stream_id': 'camera_MAIN', 'file_path': str(segment),
                })
                self.assertEqual(request.get_method(), 'POST')
                probe.assert_not_called()
                rename.assert_not_called()
            self.assertEqual(segment.read_bytes(), b'original recording bytes')


if __name__ == '__main__':
    unittest.main()
