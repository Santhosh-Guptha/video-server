#!/usr/bin/env python3
"""Unattended Ubuntu setup. Keeps existing data, credentials and service files."""
import argparse, hashlib, ipaddress, json, os, pwd, re, secrets, shutil
import subprocess, sys, tarfile, tempfile, time, urllib.request
from pathlib import Path

BASE = '7937d80044f76b072478197695d8a8e51dbf6891'
TESTED = 'f1eea0b85bc89b138e72fd936612ef02920cce72'
REPO = 'https://github.com/Santhosh-Guptha/video-server.git'
UPSTREAM = 'https://monolithic-portal.iviscloud.net/api/cameras/camera-videoserver'
BUNDLE = Path(__file__).resolve().parent

def run(args, **kwargs):
    subprocess.run([str(x) for x in args], check=True, **kwargs)

def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'video-server-setup'}), timeout=120) as r:
        return r.read()

def put_new(path, text, mode=0o644):
    path=Path(path)
    if path.exists(): return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text); path.chmod(mode)

def unpack_checked(url, digest, destination):
    data=fetch(url)
    if hashlib.sha256(data).hexdigest()!=digest: raise RuntimeError('Download SHA256 mismatch')
    with tempfile.NamedTemporaryFile() as archive:
        archive.write(data); archive.flush()
        with tarfile.open(archive.name) as tf:
            root=Path(destination).resolve()
            for item in tf.getmembers():
                if not (root/item.name).resolve().is_relative_to(root): raise RuntimeError('Unsafe archive path')
                if item.issym() or item.islnk():
                    link=(root/item.name).parent/item.linkname if item.issym() else root/item.linkname
                    if not link.resolve().is_relative_to(root): raise RuntimeError('Unsafe archive link')
            tf.extractall(destination)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=['all','install','setup','check','network'],default='all')
    p.add_argument('--user',default=os.environ.get('SUDO_USER') or 'santhosh')
    p.add_argument('--directory')
    p.add_argument('--lan-ip',required=True)
    args=p.parse_args()
    ipaddress.ip_address(args.lan_ip)
    account=pwd.getpwnam(args.user)
    root=Path(args.directory or (account.pw_dir+'/video-server')).resolve()
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+',str(root)) or str(root) in ['/', '/home', '/opt']:
        raise RuntimeError('Use a dedicated installation directory without spaces')
    if args.mode=='check':
        for service in ['video-backend','mediamtx','coturn','nginx','redis-server']:
            run(['systemctl','is-active',service])
        for path in ['/health','/api/policy','/api/settings/streaming']:
            with urllib.request.urlopen('http://127.0.0.1:5173'+path,timeout=20) as r:
                print(path,r.status)
        print('Application services healthy; camera availability is checked separately.')
        return
    if os.geteuid()!=0: raise RuntimeError('Run from root or with sudo; setup does not store an administrator password')
    if not Path('/run/systemd/system').exists(): raise RuntimeError('Systemd must be enabled in Ubuntu/WSL before setup')
    owner=f'{args.user}:{account.pw_gid}'
    def user_run(command,cwd=None): run(['runuser','-u',args.user,'--',*command],cwd=cwd)
    if args.mode=='network':
        # Refresh only this application's advertised addresses when WSL changes IP.
        local_ip=subprocess.check_output(['hostname','-I'],text=True).split()[0]
        config_script='''import pathlib, sys, yaml, subprocess
p=pathlib.Path('/opt/mediamtx/mediamtx.yml')
data=yaml.safe_load(p.read_text())
hosts=[sys.argv[1],sys.argv[2],'localhost','127.0.0.1']
changed=data.get('webrtcAdditionalHosts')!=hosts
if changed:
 data['webrtcAdditionalHosts']=hosts
 p.write_text(yaml.safe_dump(data,sort_keys=False))
 subprocess.run(['systemctl','restart','mediamtx'],check=True)
override=pathlib.Path('/etc/systemd/system/video-backend.service.d/network.conf')
text='[Service]\\nEnvironment="TURN_SERVER_URL=turn:'+sys.argv[2]+':3478?transport=tcp"\\n'
if not override.exists() or override.read_text()!=text:
 override.parent.mkdir(parents=True,exist_ok=True); override.write_text(text)
 subprocess.run(['systemctl','daemon-reload'],check=True)
 subprocess.run(['systemctl','restart','video-backend'],check=True)
'''
        run([root/'backend/venv/bin/python','-c',config_script,local_ip,args.lan_ip])
        return

    if args.mode in ['all','install']:
        env={**os.environ,'DEBIAN_FRONTEND':'noninteractive','NEEDRESTART_MODE':'a'}
        required=['git','curl','xz','python3','ffmpeg','nginx','redis-server','turnserver']
        missing=[name for name in required if shutil.which(name) is None]
        venv_available=subprocess.run(['python3','-c','import venv, ensurepip'],capture_output=True).returncode==0
        if missing or not venv_available or not Path('/etc/ssl/certs/ca-certificates.crt').exists():
            if not Path('/var/lib/dpkg/status').exists():
                raise RuntimeError('Ubuntu package database is missing; restore the distribution before installing missing system dependencies')
            run(['apt-get','update'],env=env)
            run(['apt-get','install','-y','git','curl','ca-certificates','xz-utils','python3-venv','python3-pip','ffmpeg','nginx','redis-server','coturn'],env=env)
        else:
            print('Required system executables already available; preserving installed system packages.',flush=True)
        if not root.exists():
            root.parent.mkdir(parents=True,exist_ok=True)
            root.mkdir(); shutil.chown(root,args.user,account.pw_gid)
            user_run(['git','init',str(root)])
            user_run(['git','remote','add','origin',REPO],root)
            user_run(['git','fetch','--depth','1','origin',TESTED],root)
            user_run(['git','checkout','-b','develop','FETCH_HEAD'],root)
        elif not (root/'.git').is_dir(): raise RuntimeError('Installation directory exists but is not the application checkout')
        current=subprocess.check_output(['runuser','-u',args.user,'--','git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        if current not in (BASE, TESTED) and subprocess.run(['runuser','-u',args.user,'--','git','-C',str(root),'merge-base','--is-ancestor',TESTED,current],check=False).returncode!=0: raise RuntimeError('Existing checkout does not descend from the tested develop revision')
        backup=Path('/var/backups/video-server')/time.strftime('setup-%Y%m%d-%H%M%S')
        for source in (BUNDLE/'patch-src').rglob('*'):
            if not source.is_file() or '__pycache__' in source.parts: continue
            target=root/source.relative_to(BUNDLE/'patch-src')
            if target.exists():
                saved=backup/source.relative_to(BUNDLE/'patch-src');saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);shutil.chown(target,args.user,account.pw_gid)
        node=Path('/opt/video-server-node/bin/node')
        if not node.exists():
            arch={'x86_64':'x64','aarch64':'arm64'}[os.uname().machine]
            sums=fetch('https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt').decode()
            digest,filename=next(line.split() for line in sums.splitlines() if line.endswith(f'-linux-{arch}.tar.xz'))
            with tempfile.TemporaryDirectory() as tmp:
                unpack_checked('https://nodejs.org/dist/latest-v22.x/'+filename,digest,tmp)
                shutil.copytree(Path(tmp)/filename.removesuffix('.tar.xz'),'/opt/video-server-node',symlinks=True)
        for name in ['npm','npx']:
            command=Path('/opt/video-server-node/bin')/name
            target=f'../lib/node_modules/npm/bin/{name}-cli.js'
            if command.exists() and not command.is_symlink():
                command.unlink()
                command.symlink_to(target)
        media=Path('/opt/mediamtx/mediamtx')
        version=subprocess.check_output([str(media),'--version'],text=True).strip() if media.exists() else ''
        if version!='v1.21.0':
            arch={'x86_64':'amd64','aarch64':'arm64'}[os.uname().machine]
            release=json.loads(fetch('https://api.github.com/repos/bluenviron/mediamtx/releases/tags/v1.21.0'))
            asset=next(a for a in release['assets'] if a['name']==f'mediamtx_v1.21.0_linux_{arch}.tar.gz')
            digest=asset.get('digest','')
            if not digest.startswith('sha256:'): raise RuntimeError('Release did not provide a verifiable SHA256 digest')
            with tempfile.TemporaryDirectory() as tmp:
                unpack_checked(asset['browser_download_url'],digest.split(':')[1],tmp)
                media.parent.mkdir(parents=True,exist_ok=True)
                if media.exists(): backup.mkdir(parents=True,exist_ok=True);shutil.copy2(media,backup/'mediamtx')
                staged=media.with_suffix('.new');shutil.copy2(Path(tmp)/'mediamtx',staged);staged.chmod(0o755);staged.replace(media)
        if not (root/'backend/venv/bin/python').exists(): user_run(['python3','-m','venv',str(root/'backend/venv')])
        user_run([str(root/'backend/venv/bin/pip'),'install','-r',str(root/'backend/requirements.txt'),'PyYAML==6.0.3'])
        user_run([str(root/'backend/venv/bin/pip'),'check'])
        user_run(['/usr/bin/env','PATH=/opt/video-server-node/bin:/usr/local/bin:/usr/bin:/bin','npm','ci'],root/'frontend')

    if args.mode in ['all','setup']:
        if not (root/'backend/venv/bin/python').exists(): raise RuntimeError('Run install or all mode first')
        data=root/'backend/data';data.mkdir(exist_ok=True);shutil.chown(data,args.user,account.pw_gid)
        put_new(root/'backend/.env',f'''DATABASE_URL=sqlite+aiosqlite:///./data/develop.db
REDIS_URL=redis://127.0.0.1:6379/1
UPSTREAM_CAMERA_API_URL={UPSTREAM}
TURN_SERVER_URL=turn:{args.lan_ip}:3478?transport=tcp
TURN_SERVER_USERNAME=video-viewer
TURN_SERVER_CREDENTIAL={secrets.token_urlsafe(32)}
GRID_VIEW_PROFILE=HD
FOCUS_VIEW_PROFILE=HD
LIVE_STREAM_PROFILE=HD
PLAYBACK_PROFILE=HD
WEBRTC_CONNECTION_TIMEOUT_SECONDS=20
''',0o600)
        shutil.chown(root/'backend/.env',args.user,account.pw_gid)
        # Existing installations retain their credentials and coturn configuration.
        env_values=dict(line.split('=',1) for line in (root/'backend/.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
        if not Path('/etc/systemd/system/video-backend.service').exists():
            put_new('/etc/video-server/turnserver.conf',f'''listening-port=3478
fingerprint
lt-cred-mech
realm=video-server
user={env_values.get('TURN_SERVER_USERNAME','video-viewer')}:{env_values.get('TURN_SERVER_CREDENTIAL','')}
no-tls
no-dtls
''',0o640)
            shutil.chown('/etc/video-server/turnserver.conf','turnserver','turnserver')
            put_new('/etc/systemd/system/coturn.service.d/video-server.conf','''[Service]
ExecStart=
ExecStart=/usr/bin/turnserver -c /etc/video-server/turnserver.conf
''')
        local_ip=subprocess.check_output(['hostname','-I'],text=True).split()[0]
        media_config=Path('/opt/mediamtx/mediamtx.yml')
        put_new(media_config,f'''logLevel: info
api: yes
apiAddress: 127.0.0.1:9997
rtspAddress: :8554
rtspTransports: [tcp]
hlsAddress: :8080
hlsVariant: lowLatency
webrtcAddress: :8889
webrtcLocalUDPAddress: :8189
webrtcLocalTCPAddress: :8000
webrtcAdditionalHosts: [{local_ip}, {args.lan_ip}]
webrtcICEServers2: []
moq: no
pathDefaults:
  rtspTransport: tcp
  record: yes
  recordPath: {root}/backend/data/recordings/%path/%Y-%m-%d/%Y%m%d_%H%M%S_live
  recordFormat: fmp4
  recordSegmentDuration: 60s
  runOnRecordSegmentComplete: /bin/bash {root}/backend/app/segment_hook.sh "$MTX_PATH" "$MTX_SEGMENT_PATH"
paths: {{}}
''',0o640)
        shutil.chown(media_config,args.user,account.pw_gid)
        put_new('/etc/systemd/system/mediamtx.service',f'''[Unit]
Description=Video server MediaMTX
After=network-online.target
[Service]
User={args.user}
WorkingDirectory={root}/backend
ExecStart=/opt/mediamtx/mediamtx /opt/mediamtx/mediamtx.yml
Restart=on-failure
[Install]
WantedBy=multi-user.target
''')
        put_new('/etc/systemd/system/video-backend.service',f'''[Unit]
Description=Camera Video Platform Backend
After=network-online.target mediamtx.service redis-server.service
Wants=mediamtx.service redis-server.service
[Service]
User={args.user}
WorkingDirectory={root}/backend
ExecStart={root}/backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8006
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
UMask=0027
[Install]
WantedBy=multi-user.target
''')
        put_new('/etc/nginx/sites-available/video-server','''server {
 listen 5173;
 root /var/www/video-server;
 index index.html;
 location / { try_files $uri $uri/ /index.html; }
 location /api/ { proxy_pass http://127.0.0.1:8006; proxy_http_version 1.1; proxy_set_header Host $host; proxy_read_timeout 120s; proxy_buffering off; }
 location = /health { proxy_pass http://127.0.0.1:8006; }
 location /ws/ { proxy_pass http://127.0.0.1:8006; proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; proxy_read_timeout 3600s; }
}
''')
        link=Path('/etc/nginx/sites-enabled/video-server')
        if not link.exists():link.symlink_to('/etc/nginx/sites-available/video-server')
        user_run(['/usr/bin/env','PATH=/opt/video-server-node/bin:/usr/local/bin:/usr/bin:/bin','npm','run','build'],root/'frontend')
        shutil.copytree(root/'frontend/dist','/var/www/video-server',dirs_exist_ok=True)
        run(['nginx','-t']);run(['systemctl','daemon-reload'])
        run(['systemctl','enable','--now','redis-server','coturn','mediamtx','nginx','video-backend'])
        run(['systemctl','restart','mediamtx','video-backend']);run(['systemctl','reload','nginx'])
        for _ in range(60):
            try:
                with urllib.request.urlopen('http://127.0.0.1:5173/health',timeout=3) as response:
                    if response.status==200:break
            except Exception:time.sleep(2)
        else:raise RuntimeError('Backend health check failed; inspect journalctl -u video-backend')
        print(f'Setup complete: http://{args.lan_ip}:5173/ — open Streaming Settings to review policy.')

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(f'Setup failed: {error}',file=sys.stderr);sys.exit(1)
