#!/usr/bin/env python3
"""Audit every tracked/staged file before publication. Never reads Git credentials."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
ALLOW={'.md','.txt','.py','.sh','.json','.prop'}
SPECIAL={'.gitignore','.gitattributes','LICENSE'}
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
findings=[];files=[]
for name in names:
    path=ROOT/name
    if path.is_symlink() or not path.is_file() or ROOT not in path.resolve().parents:
        findings.append((name,'invalid_path'));continue
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
report={'files':len(files),'bytes':sum(f['bytes'] for f in files),'binary_files':0,
        'findings':findings,'scope':'all tracked files; text-only allowlist, token/key/path/address scan and relative links'}
print(json.dumps(report,ensure_ascii=False,indent=2))
if findings: sys.exit(1)
