"""Host-independent identity/API tests using mocked bcrypt and Linux commands.
Real bcrypt, sshd and ACL integration still require an Unraid container test.
"""
import hashlib
import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Local test shim only; released container uses apt python3-bcrypt.
fake = types.ModuleType('bcrypt')
fake.gensalt = lambda rounds=12: b'$2b$12$fake'
fake.hashpw = lambda pw, salt: b'$2b$12$' + hashlib.sha256(pw).hexdigest().encode()
fake.checkpw = lambda pw, hashed: fake.hashpw(pw, b'') == hashed
sys.modules['bcrypt'] = fake
os.environ['MANAGER_TOKEN'] = 'T' * 48
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'docker'))
a = importlib.import_module('user_accounts')
s = importlib.import_module('supervisor')

class UserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.patches = [patch.object(a,'AUTH_DIR',base),patch.object(a,'USERS_FILE',base/'users.json'),
                        patch.object(a,'HTPASSWD',base/'users.htpasswd'),patch.object(a,'ACL_MARKER',base/'marker'),
                        patch.object(a,'_os_exists',return_value=False),patch.object(a,'_sync_user'),
                        patch.object(a,'_set_game_permissions'),
                        patch.object(a,'_run',return_value='$6$fake$hash\n')]
        for p in self.patches: p.start(); self.addCleanup(p.stop)
        a.SESSIONS.clear()

    def test_create_login_and_file_mode(self):
        result = a.create('friend', 'very-long-secret-pass')
        self.assertEqual(result['username'],'friend')
        self.assertTrue(a.verify('friend','very-long-secret-pass'))
        self.assertFalse(a.verify('friend','wrong'))
        sid = a.login('friend','very-long-secret-pass')
        self.assertEqual(a.session_username(sid),'friend')
        self.assertEqual((a.USERS_FILE).stat().st_mode & 0o777,0o600)
        self.assertEqual((a.HTPASSWD).stat().st_mode & 0o777,0o600)
        self.assertIn('friend:$2b$',a.HTPASSWD.read_text())
        self.assertNotIn('very-long-secret-pass', a.USERS_FILE.read_text())

    def test_disable_revokes_session(self):
        a.create('friend', 'very-long-secret-pass')
        sid=a.login('friend','very-long-secret-pass')
        a.modify('friend',enabled=False)
        self.assertIsNone(a.session_username(sid))
        self.assertFalse(a.verify('friend','very-long-secret-pass'))
        self.assertNotIn('friend:',a.HTPASSWD.read_text())

    def test_password_change_invalidates_session(self):
        a.create('friend','very-long-secret-pass')
        sid=a.login('friend','very-long-secret-pass')
        a.change_password('friend','another-very-long-secret')
        self.assertIsNone(a.session_username(sid))
        self.assertFalse(a.verify('friend','very-long-secret-pass'))
        self.assertTrue(a.verify('friend','another-very-long-secret'))

    def test_name_validation_and_reserved(self):
        for invalid in ['root','scum','Admin','../foo','a','my friend']:
            with self.assertRaises(ValueError): a.create(invalid,'very-long-secret-pass')

    def test_delete_removes_registry_but_not_files(self):
        a.create('friend','very-long-secret-pass')
        a.delete('friend')
        self.assertEqual(a.list_users(),[])

    def test_admin_only_routing(self):
        from http.server import ThreadingHTTPServer
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        import threading
        a.create('friend','very-long-secret-pass')
        srv=ThreadingHTTPServer(('127.0.0.1',0),s.ManagerHandler)
        thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
        self.addCleanup(srv.server_close);self.addCleanup(srv.shutdown)
        url=f'http://127.0.0.1:{srv.server_port}'
        def call(path,method='GET',data=None,headers=None):
            header=dict(headers or {})
            if method=='POST': header['X-SCUM-Request']='1';header['Content-Type']='application/json'
            req=Request(url+path,method=method,headers=header,data=json.dumps(data).encode() if data is not None else None)
            try:
                with urlopen(req,timeout=3) as r:return r.status,json.loads(r.read()),r.headers
            except HTTPError as e:return e.code,json.loads(e.read()),e.headers
        code,_,headers=call('/api/login','POST',{'username':'friend','password':'very-long-secret-pass'})
        self.assertEqual(code,200)
        cookie=headers.get('Set-Cookie').split(';')[0]
        self.assertIn('HttpOnly', headers.get('Set-Cookie'))
        self.assertEqual(call('/api/status',headers={'Cookie':cookie})[0],200)
        self.assertEqual(call('/api/users',headers={'Cookie':cookie})[0],403)
        self.assertEqual(call('/api/users',headers={'Authorization':'Bearer '+'T'*48})[0],200)
        self.assertEqual(call('/api/users','POST',{'username':'newuser','password':'very-long-secret-pass'},headers={'Cookie':cookie})[0],403)
        self.assertEqual(call('/api/backups',headers={'Cookie':cookie})[0],404)

if __name__=='__main__':unittest.main()
