import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import streaming_settings as module

class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.original=module.CONFIG_FILE
        module.CONFIG_FILE=Path(self.temp.name)/'settings.json'
        app=FastAPI();app.include_router(module.router)
        self.client=TestClient(app)
    def tearDown(self):
        module.CONFIG_FILE=self.original;self.temp.cleanup()
    def test_round_trip_and_persistence(self):
        value=module.StreamingSettings().model_dump()
        value['webrtc_stall_timeout_seconds']=12
        response=self.client.put('/api/settings/streaming',json=value)
        self.assertEqual(response.status_code,200)
        self.assertEqual(module.load_overrides(),value)
        self.assertEqual(self.client.get('/api/settings/streaming').json()['settings'],value)
    def test_invalid_input_does_not_write(self):
        for change in [{'max_active_transcoders':999},{'webrtc_stall_timeout_seconds':0},{'grid_view_profile':'4K'},{'turn_server_credential':'not-allowed'}]:
            value=module.StreamingSettings().model_dump();value.update(change)
            self.assertEqual(self.client.put('/api/settings/streaming',json=value).status_code,422)
        self.assertFalse(module.CONFIG_FILE.exists())

if __name__=='__main__':unittest.main()
