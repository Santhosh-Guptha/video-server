from pathlib import Path
import sys,unittest
from unittest.mock import AsyncMock,patch
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.mediamtx_client import MediaMTXClient
class MediaTests(unittest.IsolatedAsyncioTestCase):
 async def test_existing_matching_path_not_patched(self):
  config={'source':'rtsp://example.invalid/live','rtspTransport':'tcp','sourceOnDemand':False,'record':True,'runOnDemand':'','runOnUnDemand':''}
  request=AsyncMock(side_effect=[httpx.Response(400,text='already exists'),httpx.Response(200,json=config)])
  with patch('app.mediamtx_client._mtx_request',request):
   self.assertTrue(await MediaMTXClient().add_path('test',config['source']))
  self.assertEqual(request.await_count,2)
  self.assertEqual(request.call_args_list[0].kwargs['json']['rtspTransport'],'tcp')
 async def test_active_path_api(self):
  request=AsyncMock(return_value=httpx.Response(200,json={'items':[{'name':'test','ready':True}]}))
  with patch('app.mediamtx_client._mtx_request',request):
   result=await MediaMTXClient().get_active_streams()
  self.assertTrue(result['test']['ready'])
  self.assertIn('/v3/paths/list',request.call_args.args[1])
if __name__=='__main__':unittest.main()
