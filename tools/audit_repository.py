#!/usr/bin/env python3
"""Audit every tracked/staged file before publication. Never reads Git credentials."""
from pathlib import Path
import hashlib
import json
import re
import struct
import subprocess
import sys
import zlib

ROOT=Path(__file__).resolve().parents[1]
ALLOW={'.md','.txt','.py','.sh','.json','.prop'}
SPECIAL={'.gitignore','.gitattributes','LICENSE'}
# These exact images were visually reviewed for account and network details.
SCREENSHOTS={
    'docs/screenshots/01-dap-max-plus.png':'42d3ff20abd05cb348556b954c7644427384de309fbe59ddf04aef07d7f6979f',
    'docs/screenshots/02-dark-settings.png':'5666abe720d6d4eba4d7008773279c7931f14c71aec78cfc03d2d13e25acdabc',
    'docs/screenshots/03-projection.png':'1dc42dfdbda904a71cc5091acf26b7ddfcb5bbea6e118b47a9f6d49e4125fa84',
    'docs/screenshots/04-picture.png':'ef2c32979cac41d857ac85a5b0aad7f8727ab8b30f1066ca0868962c5cce8168',
    'docs/screenshots/05-equalizer.png':'882848b0e1c1d727484ab55b729ad4e3d9b85b91317e38d906ee6780811c27cb',
    'docs/screenshots/06-brightness.png':'456edf9bd4b774cbd7db611fa168b191e021812bf25592a61955d237cd8109fd',
    'docs/screenshots/07-four-corners.png':'062f17967a347b067da7ce90cde02c7a039bbd3613f4ebbd641540b7422eb717',
    'docs/screenshots/08-image-scale.png':'34f6af1685d293e359886a45f17aee3d8e1ec3a43747f284431a886dcfd1e345',
    'docs/screenshots/09-image-check.png':'46fd61ece7cfe0844883a444675bda3e36a47a7b4e3ed3b9d79e659c0b042d32',
}

def reviewed_png(name, data):
    if hashlib.sha256(data).hexdigest()!=SCREENSHOTS[name]:
        return False
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data)>2_000_000:
        return False
    offset=8; kinds=[]
    while offset+12<=len(data):
        size=struct.unpack('>I',data[offset:offset+4])[0]
        kind=data[offset+4:offset+8]
        end=offset+12+size
        if end>len(data) or kind not in {b'IHDR',b'IDAT',b'IEND',b'sBIT',b'sRGB'}:
            return False
        payload=data[offset+8:offset+8+size]
        crc=struct.unpack('>I',data[offset+8+size:end])[0]
        if zlib.crc32(kind+payload)!=crc:
            return False
        if kind==b'IHDR' and (size!=13 or struct.unpack('>II',payload[:8])!=(1920,1080)):
            return False
        kinds.append(kind); offset=end
        if kind==b'IEND':
            break
    return (offset==len(data) and kinds[0:1]==[b'IHDR']
            and kinds[-1:]==[b'IEND'] and b'IDAT' in kinds)

PATTERNS={
    'private_key':re.compile(r'-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----'),
    'github_token':re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    'google_api_key':re.compile(r'\bAIza[0-9A-Za-z_-]{30,}\b'),
    'local_home_path':re.compile(r'(?:/(?:Users|home)/[A-Za-z0-9_.-]+|[A-Za-z]:\\Users\\[A-Za-z0-9_.-]+)',re.I),
    'local_ipv4':re.compile(r'(?<![\d.])(?:10\.(?:\d{1,3}\.){2}\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?![\d.])'),
    'mac_address':re.compile(r'(?i)(?<![0-9a-f])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f])'),
}
names=subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z']).decode().split('\0')
names=[n for n in names if n]
if not names: raise SystemExit('No staged/tracked files: stage the publication allowlist first.')
findings=[];files=[];screenshots=0
for name in names:
    path=ROOT/name
    if path.is_symlink() or not path.is_file() or ROOT not in path.resolve().parents:
        findings.append((name,'invalid_path'));continue
    if name in SCREENSHOTS:
        data=path.read_bytes()
        if not reviewed_png(name,data):
            findings.append((name,'unapproved_or_invalid_screenshot'));continue
        screenshots+=1
        files.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        continue
    if path.suffix.lower() not in ALLOW and name not in SPECIAL:
        findings.append((name,'forbidden_file_type'));continue
    data=path.read_bytes()
    if len(data)>262144 or b'\x00' in data:
        findings.append((name,'binary_or_large_file'));continue
    try: text=data.decode('utf-8')
    except UnicodeDecodeError:
        findings.append((name,'not_utf8'));continue
    for label,pattern in PATTERNS.items():
        if pattern.search(text): findings.append((name,label))
    # Documentation must not contain local-only file links.
    if path.suffix=='.md':
        for link in re.findall(r'\[[^\]]+\]\(([^)]+)\)',text):
            if '://' not in link and not link.startswith('#'):
                if not (path.parent/link.split('#',1)[0]).is_file(): findings.append((name,'broken_relative_link'))
    files.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
report={'files':len(files),'bytes':sum(f['bytes'] for f in files),'binary_files':screenshots,
        'approved_screenshots':screenshots,'findings':findings,
        'scope':'all tracked files; text allowlist, pinned metadata-free PNG screenshots, token/key/path/address scan and relative links'}
print(json.dumps(report,ensure_ascii=False,indent=2))
if findings: sys.exit(1)
