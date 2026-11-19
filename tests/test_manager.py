import importlib.util, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import threading
# Mock bcrypt only if it is unavailable on the host running these API tests.
# The container itself installs python3-bcrypt; integration tests use the real library.
try:
    import bcrypt
except ModuleNotFoundError:
    import hashlib, types
    fake = types.ModuleType('bcrypt')
    fake.gensalt = lambda rounds=12: b'$2b$12$fake'
    fake.hashpw = lambda pw, salt: b'$2b$12$' + hashlib.sha256(pw).hexdigest().encode()
    fake.checkpw = lambda pw, h: fake.hashpw(pw, b'') == h
    sys.modules['bcrypt'] = fake

ROOT = Path(__file__).resolve().parents[1]
os.environ['MANAGER_TOKEN'] = 'T'*48
sys.path.insert(0, str(ROOT/'docker'))
spec=importlib.util.spec_from_file_location('scum_sup',ROOT/'docker/supervisor.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
s.WEB=ROOT/'docker/web/index.html'

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),s.ManagerHandler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close()
    def call(self,path,method='GET',token=True,payload=None):
        headers={'Authorization':'Bearer '+'T'*48, 'X-SCUM-Request':'1'} if token else {'X-SCUM-Request':'1'}
        if payload is not None: headers['Content-Type']='application/json'
        req=Request(self.url+path, method=method,headers=headers,data=json.dumps(payload).encode() if payload is not None else None)
        try:
            with urlopen(req,timeout=3) as r:return r.status,json.loads(r.read()) if path!='/' else None
        except HTTPError as e:return e.code,json.loads(e.read())
    def test_dashboard(self):
        self.assertEqual(self.call('/')[0],200)
    def test_auth(self):
        for path in ['/api/status','/api/sftp','/api/logs']:
            self.assertEqual(self.call(path,token=False)[0],401)
        self.assertEqual(self.call('/api/sftp/password',method='POST',token=False,payload={'password':'a'*20})[0],401)
    def test_status_uptime(self):
        status,data=self.call('/api/status')
        self.assertEqual(status,200)
        self.assertGreaterEqual(data['supervisor_uptime_seconds'],0)
        self.assertIn('recent_exits',data)
    def test_sftp_get(self):
        with patch.object(s,'sftp_status',return_value={'account':'scum'}):
            self.assertEqual(self.call('/api/sftp'),(200,{'account':'scum'}))
    def test_backup_api_removed(self):
        self.assertEqual(self.call('/api/backups')[0],404)
        self.assertEqual(self.call('/api/actions/backup',method='POST')[0],404)
        self.assertEqual(self.call('/api/backups/restore',method='POST')[0],404)
    def test_password_input_validation(self):
        for invalid in ['short','a\nb'*9]:
            code,_=self.call('/api/sftp/password',method='POST',payload={'password':invalid})
            self.assertEqual(code,400)
    def test_password_queued_not_echoed(self):
        while not s.PENDING.empty():s.PENDING.get_nowait()
        password='a'*24
        code,response=self.call('/api/sftp/password',method='POST',payload={'password':password})
        self.assertEqual(code,202)
        self.assertEqual(s.PENDING.get_nowait(),('sftp_password',password))
        self.assertNotIn(password,json.dumps(response))
        self.assertNotIn(password,' '.join(s.RECENT))
    def test_rotate_persist_hash(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(s,'SFTP_SHADOW',Path(td)/'scum-password.hash'), patch.object(s.subprocess,'run') as run:
                run.side_effect=[MagicMock(returncode=0),MagicMock(returncode=0,stdout='scum:$6$salt$hash:1:2:3:4:5:6:7\n')]
                s.rotate_sftp_password('A'*24)
                self.assertEqual((Path(td)/'scum-password.hash').read_text(),'$6$salt$hash\n')
                self.assertEqual((Path(td)/'scum-password.hash').stat().st_mode & 0o777,0o600)
                self.assertNotIn('A'*24,(Path(td)/'scum-password.hash').read_text())

if __name__=='__main__': unittest.main()
