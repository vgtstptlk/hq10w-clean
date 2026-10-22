#!/usr/bin/env python3
"""Package the verified full OTA, original factory rollback and USB launcher; never reads a device."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import zipfile

REPO=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
WORK=REPO/'release-work/hq10w-full'
DIST=REPO/'releases/HQ10W-Clean-Full-1'
USB=DIST/'USB-root'
HELP=USB/'HQ10W-Full'
OEM=REPO/'backup/everycom-hq10w-2026-10-21'
FACTORY=OEM/'optimization/vendor-ota/factory-update.zip'
OTA=USB/'HQ10W-Clean-Full-1.zip'
PAYLOAD=REPO/'releases/HQ10W-Clean-1/USB-root/HQ10W-Clean'

def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

report=json.loads((DIST/'VERIFICATION.json').read_text())
assert report['signature_cryptographically_valid'] and report['signer_matches_oem_and_recovery']
assert report['sha256']==sha(OTA)
assert 'SHA1/RSA' in report['signature_algorithm']
assert sha(FACTORY)=='943268ea81004580476cfbf2069c212996d852f5dbc08a3533a6f97f11bfc292'
HELP.mkdir(exist_ok=True)
shutil.copyfile(HERE/'check-board.sh',HELP/'check-board.sh')
rollback=(HERE/'rollback-prep.sh').read_text().replace('@RESTORE_SHA256@',sha(PAYLOAD/'audio/restore.sh'))
(HELP/'rollback-prep.sh').write_text(rollback)
entry=(HERE/'usb-start.sh').read_text().replace('@GUARD_SHA256@',sha(HELP/'check-board.sh'))
entry=entry.replace('@OTA_SHA256@',sha(OTA)).replace('@ROLLBACK_PREP_SHA256@',sha(HELP/'rollback-prep.sh'))
assert '@OTA_' not in entry and '@GUARD_' not in entry and '@ROLLBACK_' not in entry
(USB/'newlink_update.sh').write_text(entry)
(USB/'MODE.txt').write_text('CHECK\n')
shutil.copyfile(FACTORY,HELP/'factory-V1.0.3.6.zip')
assert sha(HELP/'factory-V1.0.3.6.zip')==sha(FACTORY)
shutil.copyfile(REPO/'README-RU.txt',DIST/'README-RU.txt')
for document in ('CHANGES-RU.txt','INSTALL-RU.txt'):
    shutil.copyfile(REPO/document,DIST/document)
    shutil.copyfile(REPO/document,HELP/document)
shutil.copyfile(WORK/'guard-checks.json',DIST/'BOARD-GUARD-CHECK.json')
if (WORK/'usb-guard-checks.json').exists():
    shutil.copyfile(WORK/'usb-guard-checks.json',DIST/'USB-GUARD-CHECK.json')

# Scan all changed image file readbacks, including nested APK entries, for local identifiers.
patterns=(b'/users/',b'/home/',b'-----begin private key',b'-----begin rsa private key')
def scan(label,data):
    lower=data.lower()
    for term in patterns: assert term not in lower,(label,term)

for path in (WORK/'readback').rglob('*'):
    if path.is_file():
        scan(path.name,path.read_bytes())
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                for name in z.namelist(): scan(path.name+'/'+name,z.read(name))
for path in DIST.rglob('*'):
    if path.is_file() and path.suffix!='.zip': scan(path.name,path.read_bytes())
for path in USB.rglob('*.sh'):
    subprocess.run(['/bin/sh','-n',str(path)],check=True)

package_report={
    'base_sha256':sha(FACTORY),
    'input_type':'official factory images and staged APK/audio inputs',
    'signature_verified':True,
    'host_guard_checks':'see board and USB reports',
}
(DIST/'PACKAGE-CHECK.json').write_text(json.dumps(package_report,indent=2)+'\n')
checksums=DIST/'SHA256SUMS.txt'
checksums.write_text(''.join(f'{sha(p)}  {p.relative_to(DIST).as_posix()}\n' for p in sorted(DIST.rglob('*')) if p.is_file() and p!=checksums))
# Fixed generic timestamps and permissions, no macOS resource forks, extra fields or absolute paths.
archive=DIST.parent/'HQ10W-Clean-Full-1-USB.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_STORED,allowZip64=True) as z:
    for p in sorted(DIST.rglob('*')):
        if not p.is_file(): continue
        relative=p.relative_to(DIST).as_posix()
        assert not p.is_symlink() and '..' not in Path(relative).parts
        assert p.suffix not in ('.img','.bin','.pk8','.pem','.keystore','.db','.sqlite')
        info=zipfile.ZipInfo(relative,(2026,10,22,0,0,0));info.external_attr=0o100644<<16
        info.compress_type=zipfile.ZIP_STORED
        with p.open('rb') as source,z.open(info,'w') as target:
            shutil.copyfileobj(source,target,1048576)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert z.read('USB-root/MODE.txt')==b'CHECK\n'
    for line in z.read('SHA256SUMS.txt').decode().splitlines():
        expected,relative=line.split('  ',1)
        with z.open(relative) as source: assert hashlib.file_digest(source,'sha256').hexdigest()==expected,relative
result={'usb_archive':archive.name,'bytes':archive.stat().st_size,'sha256':sha(archive),
        'full_ota_bytes':OTA.stat().st_size,'full_ota_sha256':sha(OTA),'default_mode':'CHECK','archive_integrity':'passed'}
(WORK/'distribution.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
