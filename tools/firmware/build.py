#!/usr/bin/env python3
"""Offline full non-A/B OTA builder. No ADB, live-device reads or partition writes."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import zipfile

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OEM = REPO/'backup/everycom-hq10w-2026-10-21'
SOURCE = OEM/'optimization/vendor-ota/factory-update.zip'
WORK = REPO/'release-work/hq10w-full'
STOCK = OEM/'compatibility/ota'
PAYLOAD = REPO/'releases/HQ10W-Clean-1/USB-root/HQ10W-Clean'
DIST = REPO/'releases/HQ10W-Clean-Full-1'
OTA_NAME = 'HQ10W-Clean-Full-1.zip'
DEBUGFS = REPO/'backup/build-tools/e2fsprogs-1.47.4/debugfs/debugfs'
FSCK = REPO/'backup/build-tools/e2fsprogs-1.47.4/e2fsck/e2fsck'
OPENSSL = '/opt/homebrew/bin/openssl'
FACTORY_SHA = '943268ea81004580476cfbf2069c212996d852f5dbc08a3533a6f97f11bfc292'
IMAGE_SHA = {'system':'2291f2189c21e849d1f20e2d1b6e577194e623dbef178fca789fa452566ff9e9',
             'vendor':'9a681e4b88dd3954c74f627cd5a16f456daf3bfd7902dfe3a017b47c308cab64'}
EPOCH = 1792627200  # 2026-10-22 00:00 UTC, generic release timestamp.
WORK.mkdir(exist_ok=True, parents=True)

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)

def debug(image, command, write=False):
    result = subprocess.run([str(DEBUGFS), *(['-w'] if write else []), '-R', command, str(image)], text=True, capture_output=True)
    with (WORK/'debugfs.log').open('a') as log:
        log.write(command+'\n'+result.stdout+result.stderr+'\n')
    bad = ('not found by ext2_lookup','not found by ext2_lookup','file not found','could not','while ','invalid argument','no space left','command not found','usage:')
    assert result.returncode == 0 and not any(s in result.stderr.lower() for s in bad), result.stdout+result.stderr
    return result.stdout

def q(path):
    s = str(path)
    assert not any(c in s for c in ('"','\\','\n','\r'))
    return '"'+s+'"'

def dump(image, remote, local):
    debug(image, 'dump '+remote+' '+q(local))
    assert local.is_file(), remote

def attributes(image, remote, mode, context):
    for key, value in [('mode',mode),('uid','0'),('gid','0'),('atime',str(EPOCH)),('mtime',str(EPOCH)),('ctime',str(EPOCH)),('crtime',str(EPOCH))]:
        debug(image, f'set_inode_field {remote} {key} {value}', True)
    ctx = WORK/f'{context}.context'
    ctx.write_bytes(('u:object_r:'+context+':s0\0').encode())
    debug(image, 'ea_set -f '+q(ctx)+' '+remote+' security.selinux', True)

def mkdir(image, remote, context):
    debug(image, 'mkdir '+remote, True)
    attributes(image, remote, '040755', context)

def write(image, remote, local, context, replace=False, mode='0100644'):
    if replace:
        debug(image, 'rm '+remote, True)
    debug(image, 'write '+q(local)+' '+remote, True)
    attributes(image, remote, mode, context)
    checked = WORK/'readback'/image.stem/remote.lstrip('/')
    checked.parent.mkdir(exist_ok=True, parents=True)
    dump(image, remote, checked)
    assert sha(checked) == sha(local), remote
    return {'path':remote,'sha256':sha(local),'bytes':local.stat().st_size,'selinux':'u:object_r:'+context+':s0'}

def images():
    assert sha(SOURCE) == FACTORY_SHA
    report = {'base_sha256':FACTORY_SHA, 'source':'official OEM full OTA only; no live device dump', 'changed_files':[], 'removed_files':[]}
    for part in ('system','vendor'):
        source = STOCK/f'{part}.img'
        assert sha(source) == IMAGE_SHA[part], part
        shutil.copyfile(source, WORK/f'{part}.img')
    system = WORK/'system.img'; vendor = WORK/'vendor.img'
    # Use APK inputs prepared by the customization packaging step.
    for folder, name in [('CleanTVHome','home'),('HQ10WDAP','dap')]:
        mkdir(system, f'/system/app/{folder}', 'system_file')
        report['changed_files'].append(write(system, f'/system/app/{folder}/{folder}.apk', PAYLOAD/f'apks/{name}.apk', 'system_file'))
    report['changed_files'].append(write(system, '/system/app/NLSetting_V2/NLSetting_V2.apk', PAYLOAD/'apks/settings.apk', 'system_file', True))
    for name in ('NLSetting_V2.odex','NLSetting_V2.vdex'):
        remote='/system/app/NLSetting_V2/oat/arm/'+name
        debug(system, 'rm '+remote, True); report['removed_files'].append(remote)
    debug(system, 'rmdir /system/app/NLSetting_V2/oat/arm', True)
    debug(system, 'rmdir /system/app/NLSetting_V2/oat', True)
    for directory in ('/etc/hq10w-clean','/etc/hq10w-clean/audio'):
        mkdir(vendor, directory, 'vendor_configs_file')
    for path in sorted((PAYLOAD/'audio').iterdir()):
        context = 'vendor_file' if path.suffix in ('.so','.jar','.sh') else 'vendor_configs_file'
        report['changed_files'].append(write(vendor, '/etc/hq10w-clean/audio/'+path.name, path, context))
    home = WORK/'hq10w-clean-home.sh'
    home.write_text((HERE/'home.sh').read_text().replace('@HOME_SHA256@',sha(PAYLOAD/'apks/home.apk')))
    report['changed_files'].append(write(vendor, '/bin/hq10w-clean-home.sh', home, 'vendor_file', mode='0100755'))
    report['changed_files'].append(write(vendor, '/bin/hq10w-clean-first-boot.sh', HERE/'first-boot.sh', 'vendor_file', mode='0100755'))
    init_original = WORK/'stock/init.bigfish.rc'; init_original.parent.mkdir(exist_ok=True)
    dump(vendor, '/etc/init/hw/init.bigfish.rc', init_original)
    text = init_original.read_text()
    needle = '    # Start essential services\n'
    assert text.count(needle) == 1
    text = text.replace(needle, '    # HQ10W Clean: select Home before the untouched OEM provisioning wrapper starts.\n'
        '    exec u:r:vendor_shell:s0 root root -- /vendor/bin/sh /vendor/bin/hq10w-clean-home.sh\n\n'+needle)
    needle = 'on property:sys.boot_completed=1\n'
    assert text.count(needle) == 1
    text = text.replace(needle, needle+'    exec u:r:vendor_shell:s0 root root -- /vendor/bin/sh /vendor/bin/hq10w-clean-first-boot.sh\n')
    modified = WORK/'init.bigfish.rc'; modified.write_text(text)
    report['changed_files'].append(write(vendor, '/etc/init/hw/init.bigfish.rc', modified, 'vendor_configs_file', True))
    label = WORK/'hq10w-clean-release.txt'
    label.write_text('HQ10W Clean Full 1\nBase: OEM V1.0.3.6\nProject: YG_5H080_693_RX_ZX\nBased on factory V1.0.3.6.\n')
    report['changed_files'].append(write(system,'/system/etc/hq10w-clean-release.txt',label,'system_file'))
    for part in ('system','vendor'):
        image = WORK/f'{part}.img'
        debug(image,'set_super_value wtime '+str(EPOCH), True)
        check = subprocess.run([str(FSCK),'-fn',str(image)],capture_output=True,text=True)
        (WORK/f'{part}-fsck.txt').write_text(check.stdout+check.stderr)
        assert check.returncode == 0, check.stdout+check.stderr
        report[part] = {'bytes':image.stat().st_size,'sha256':sha(image),'fsck':'passed'}
    # Record the verified build inputs.
    report['preserved_factory_fallback'] = ['NLProvision','Whale launcher','stock audio config','thermal service','firmware updater']
    (WORK/'images.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Full system/vendor images built; file readbacks and both ext4 checks passed.',flush=True)

def streams():
    report={}
    for part in ('system','vendor'):
        raw=WORK/f'{part}.img'; blocks=raw.stat().st_size//4096
        assert raw.stat().st_size%4096==0
        # Full coverage, only "new" commands: no source-version dependency, patching or stashes.
        commands=[f'new 2,{a},{min(a+1024,blocks)}' for a in range(0,blocks,1024)]
        (WORK/f'{part}.transfer.list').write_text(f'4\n{blocks}\n0\n0\n'+'\n'.join(commands)+'\n')
        compressed=WORK/f'{part}.new.dat.br'
        print('Compressing full '+part+' image...',flush=True)
        run('/opt/homebrew/bin/brotli','-f','-q','6','-w','24','-o',compressed,raw)
        # Verify the decoder consumes the complete stream and yields the exact image bytes.
        p=subprocess.Popen(['/opt/homebrew/bin/brotli','-d','-c',str(compressed)],stdout=subprocess.PIPE)
        digest=hashlib.sha256(); size=0
        while block:=p.stdout.read(1048576): digest.update(block);size+=len(block)
        assert p.wait()==0 and size==raw.stat().st_size and digest.hexdigest()==sha(raw)
        (WORK/f'{part}.patch.dat').write_bytes(b'')
        report[part]={'full_blocks':blocks,'commands':len(commands),'raw_bytes':size,'stream_sha256':sha(compressed),'decompression_matches_image':True}
    (WORK/'streams.json').write_text(json.dumps(report,indent=2)+'\n')

def ota():
    DIST.mkdir(exist_ok=True,parents=True);(DIST/'USB-root').mkdir(exist_ok=True)
    with zipfile.ZipFile(SOURCE) as original:
        script=original.read('META-INF/com/google/android/updater-script').decode()
        preflight='''ui_print("HQ10W Clean Full 1: validating board before any partition writes...");
is_mounted("/vendor") || mount("ext4", "EMMC", "/dev/block/platform/soc/f9830000.emmc/by-name/vendor", "/vendor") || abort("HQ10W: cannot mount current vendor for board validation.");
assert(package_extract_file("hq10w/check-board.sh", "/tmp/hq10w-check-board.sh"));
assert(run_program("/system/bin/sh", "/tmp/hq10w-check-board.sh") == "0");
unmount("/vendor") || abort("HQ10W: vendor must be unmounted before writing.");
if is_mounted("/system") then
  unmount("/system") || abort("HQ10W: system must be unmounted before writing.");
endif;
'''
        # Keep the stock anti-downgrade and product checks before our additional guard.
        lines=script.splitlines(keepends=True)
        assert 'E3003' in lines[0] and 'E3004' in lines[1]
        script=''.join(lines[:2])+preflight+''.join(lines[2:])
        # Every raw partition write is now checked; never report success after a failed extraction.
        script=re.sub(r'(?m)^package_extract_file\(("[^"\n]+", "/dev/block/[^"\n]+")\);$',
            r'assert(package_extract_file(\1));',script)
        script+='\nui_print("HQ10W Clean Full 1 installed; first boot can take several minutes.");\n'
        (WORK/'updater-script').write_text(script)
        # Offsets in the original protobuf metadata refer to the old ZIP; omit that optional file.
        metadata=original.read('META-INF/com/android/metadata').decode()
        metadata='\n'.join(line for line in metadata.splitlines() if not line.startswith('ota-property-files='))+'\n'
        (WORK/'metadata').write_text(metadata)
        replaced={'system.new.dat.br','vendor.new.dat.br','system.transfer.list','vendor.transfer.list','system.patch.dat','vendor.patch.dat',
                  'META-INF/com/google/android/updater-script','META-INF/com/android/metadata','META-INF/com/android/metadata.pb'}
        unsigned=WORK/'full-unsigned.zip'
        with zipfile.ZipFile(unsigned,'w',allowZip64=False) as z:
            for entry in original.infolist():
                if entry.filename in replaced: continue
                info=zipfile.ZipInfo(entry.filename,(2009,1,1,0,0,0));info.compress_type=entry.compress_type
                info.external_attr=entry.external_attr
                z.writestr(info,original.read(entry.filename))
            for part in ('system','vendor'):
                for suffix in ('new.dat.br','transfer.list','patch.dat'):
                    path=WORK/f'{part}.{suffix}'
                    z.write(path,path.name,compress_type=zipfile.ZIP_STORED if suffix in ('new.dat.br','patch.dat') else zipfile.ZIP_DEFLATED)
            z.write(WORK/'updater-script','META-INF/com/google/android/updater-script',compress_type=zipfile.ZIP_DEFLATED)
            z.write(WORK/'metadata','META-INF/com/android/metadata',compress_type=zipfile.ZIP_STORED)
            z.write(HERE/'check-board.sh','hq10w/check-board.sh',compress_type=zipfile.ZIP_DEFLATED)
            for path in sorted((PAYLOAD/'licenses').iterdir()):
                z.write(path,'hq10w/licenses/'+path.name,compress_type=zipfile.ZIP_DEFLATED)
    print('Full OTA contents assembled.',flush=True)

def spki(cert):
    pub=subprocess.check_output([OPENSSL,'x509','-in',str(cert),'-pubkey','-noout'])
    return subprocess.check_output([OPENSSL,'pkey','-pubin','-outform','DER'],input=pub)

def sign():
    keys=WORK/'signing';cert=keys/'testkey.x509.pem'
    trusted=OEM/'compatibility/signature/current-recovery-0.pem'
    assert spki(cert)==spki(trusted)==spki(OEM/'compatibility/signature/actual-signer.pem')
    pem=keys/'testkey.pem'
    run(OPENSSL,'pkcs8','-inform','DER','-nocrypt','-in',keys/'testkey.pk8','-out',pem)
    os.chmod(pem,0o600)
    unsigned=WORK/'full-unsigned.zip';output=DIST/'USB-root'/OTA_NAME
    with unsigned.open('rb') as check:
        check.seek(-22,2);assert check.read(4)==b'PK\x05\x06'  # no comment and no ZIP64
    # AOSP SignApk selects SHA1 for this legacy SHA1withRSA certificate. Recovery
    # derives the package hash algorithm from that trusted certificate as well.
    command=[OPENSSL,'cms','-sign','-binary','-noattr','-md','sha1','-signer',str(cert),'-inkey',str(pem),'-outform','DER']
    p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    with unsigned.open('rb') as source:
        remain=unsigned.stat().st_size-2
        while remain:
            block=source.read(min(remain,1048576));p.stdin.write(block);remain-=len(block)
    p.stdin.close();p.stdin=None
    signature,error=p.communicate(timeout=30)
    assert p.returncode==0,error.decode()
    message=b'signed by SignApk\0'
    comment_length=len(message)+len(signature)+6
    footer=struct.pack('<H2sH',len(signature)+6,b'\xff\xff',comment_length)
    comment=message+signature+footer
    assert len(comment)<65536 and b'PK\x05\x06' not in comment
    shutil.copyfile(unsigned,output)
    with output.open('r+b') as f:
        f.seek(-2,2);f.write(struct.pack('<H',comment_length));f.write(comment)
    (keys/'custom-whole-file-signature.der').write_bytes(signature)
    print('Whole-file OTA signature written with the OEM-trusted AOSP test key.',flush=True)

def verify():
    archive=DIST/'USB-root'/OTA_NAME;keys=WORK/'signing'
    assert spki(keys/'testkey.x509.pem')==spki(OEM/'compatibility/signature/current-recovery-0.pem')==spki(OEM/'compatibility/signature/target-recovery-0.pem')
    with archive.open('rb') as f:
        f.seek(-6,2);start,magic,length=struct.unpack('<H2sH',f.read())
        assert magic==b'\xff\xff'
        f.seek(-length-22,2);eocd=f.read()
        assert eocd[:4]==b'PK\x05\x06' and eocd[4:].find(b'PK\x05\x06')<0
        signature=eocd[-start:-6]
        der=keys/'verify.der';der.write_bytes(signature)
        p=subprocess.Popen([OPENSSL,'cms','-verify','-binary','-inform','DER','-in',str(der),'-content','/dev/stdin','-noverify','-out','/dev/null'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        f.seek(0);remain=archive.stat().st_size-length-2
        while remain:
            block=f.read(min(remain,1048576));p.stdin.write(block);remain-=len(block)
        p.stdin.close();p.stdin=None;_,error=p.communicate(timeout=30)
        assert p.returncode==0,error.decode()
        run(OPENSSL,'pkcs7','-inform','DER','-in',der,'-print_certs','-quiet','-out',keys/'verified-signer.pem')
        assert spki(keys/'verified-signer.pem')==spki(OEM/'compatibility/signature/current-recovery-0.pem')
        details=subprocess.check_output([OPENSSL,'pkcs7','-inform','DER','-in',str(der),'-print'],text=True)
        assert 'algorithm: sha1 (1.3.14.3.2.26)' in details
    with zipfile.ZipFile(SOURCE) as base,zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert z.read('META-INF/com/android/otacert')==base.read('META-INF/com/android/otacert')
        unchanged={}
        for name in ('atf.bin','boot.img','bootargs.img','bootargsbak.img','dtbo.img','fastboot.img','recovery.img','slaveboot.img','tcon.bin','META-INF/com/google/android/update-binary'):
            assert z.read(name)==base.read(name),name
            unchanged[name]=hashlib.sha256(z.read(name)).hexdigest()
        assert not any(any(x in n.lower() for x in ('userdata','securestore','deviceinfo','panelparam','wifi','account','keystore','.pk8','.pem')) for n in z.namelist())
        assert set(z.namelist())==set(base.namelist())-{'META-INF/com/android/metadata.pb'}|{'hq10w/check-board.sh'}|{'hq10w/licenses/'+p.name for p in (PAYLOAD/'licenses').iterdir()}
        script=z.read('META-INF/com/google/android/updater-script').decode()
        assert script.index('hq10w-check-board.sh')<script.index('package_extract_file("bootargsbak.img"')
        # All write destinations are explicitly allowlisted; misc changes are only the OEM stage protocol.
        destinations=set(re.findall(r'"/dev/block/platform/soc/f9830000.emmc/by-name/([a-z0-9]+)"',script))
        assert destinations=={'misc','bootargsbak','recovery','bootargs','fastboot','atf','dtbo','boot','tconparam','slaveboot','system','vendor'},destinations
        for name in ('system','vendor'):
            lines=z.read(name+'.transfer.list').decode().splitlines()
            expected=(WORK/f'{name}.img').stat().st_size//4096
            cursor=0
            for line in lines[4:]:
                op,span=line.split();count,a,b=map(int,span.split(','))
                assert op=='new' and count==2 and a==cursor and b>a
                cursor=b
            assert cursor==expected==int(lines[1])
    report={'package':archive.name,'bytes':archive.stat().st_size,'sha256':sha(archive),
        'signature_cryptographically_valid':True,'signer_spki_sha256':hashlib.sha256(spki(keys/'testkey.x509.pem')).hexdigest(),
        'signer_matches_oem_and_recovery':True,'signature_algorithm':'SHA1/RSA, whole-file detached CMS, matching the OEM legacy certificate and AOSP SignApk selection',
        'signing_key_type':'public AOSP development test key, inherited OEM trust model; not a private production key',
        'unchanged_oem_payloads':unchanged,'full_streams':json.loads((WORK/'streams.json').read_text()),
        'userdata_included':False,
        'actual_recovery_install_tested':False,'actual_clean_boot_tested':False,'actual_rollback_tested':False}
    (DIST/'VERIFICATION.json').write_text(json.dumps(report,indent=2)+'\n')
    (DIST/'IMAGE-CHANGES.json').write_text((WORK/'images.json').read_text())
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('images','streams','ota','sign','verify'))
    stage=p.parse_args().stage
    globals()[stage]()
