#!/usr/bin/env python3
"""Host simulations of USB preflight refusal paths, never an Android install test."""
from pathlib import Path
import json
import os
import subprocess
import tempfile

REPO=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
source=(HERE/'usb-start.sh').read_text().replace('@GUARD_SHA256@','expected-guard').replace('@OTA_SHA256@','expected-ota').replace('@ROLLBACK_PREP_SHA256@','expected-rollback')
passed=[]
with tempfile.TemporaryDirectory(prefix='hq10w-usb-guard-') as temporary:
    root=Path(temporary);usb=root/'VOLUME';usb.mkdir()
    mocks=root/'mocks.sh'
    mocks.write_text('''
id() { echo "${TEST_UID-0}"; }
getprop() { echo "${TEST_DATE-1733405127}"; }
sha256sum() {
 case "$1" in
 */nl_usb_update.sh) echo "${TEST_HOOK-9a220829d35bddaef067f3f76fe320d360af25f5489119e6fd0cb10b2984fbe9}  file";;
 */check-board.sh) echo "${TEST_GUARD-expected-guard}  file";;
 */HQ10W-Clean-Full-1.zip) echo "${TEST_OTA-expected-ota}  file";;
 *) echo unexpected-hash; return 1;;
 esac
}
board_guard() { [ "${TEST_BOARD-OK}" = OK ]; }
ls() { echo VOLUME; [ "${TEST_MULTIPLE-0}" != 1 ] || echo SECOND; return 0; }
awk() { case "$*" in *'print $1'*) echo /dev/usb;; *) echo "${TEST_FS-vfat}";; esac; }
stat() { echo "${TEST_BLOCK-8:1}"; }
mkdir() { echo MUTATION >&2; exit 90; }
reboot_blocked() { echo REBOOT >&2; exit 91; }
''')
    script=source.replace('export PATH=/system/bin:/system/xbin:/vendor/bin:/product/bin','. "'+str(mocks)+'"')
    script=script.replace('USB=/mnt/media_rw/$volume','USB='+str(root)+'/$volume')
    script=script.replace('/system/bin/sh "$USB/HQ10W-Full/check-board.sh"','board_guard')
    script=script.replace('/system/bin/reboot recovery','reboot_blocked')
    script=script.replace('/cache/recovery',str(root/'forbidden-cache/recovery'))
    target=root/'entry.sh';target.write_text(script)
    cases=[('matching older base',{},'CHECK_OK',0),
           ('non-root context',{'TEST_UID':'2000'},'root USB context',1),
           ('different OEM hook',{'TEST_HOOK':'other'},'different factory USB',1),
           ('damaged board guard',{'TEST_GUARD':'other'},'board guard damaged',1),
           ('board guard refused',{'TEST_BOARD':'BAD'},'',1),
           ('newer firmware',{'TEST_DATE':'1893456000'},'downgrade refused',1),
           ('multiple USB volumes',{'TEST_MULTIPLE':'1'},'only one USB',1),
           ('unsupported USB filesystem',{'TEST_FS':'exfat'},'FAT32',1),
           ('wrong USB block device',{'TEST_BLOCK':'8:11'},'sda1',1),
           ('damaged full OTA',{'TEST_OTA':'other'},'checksum failed',1)]
    for name,extra,message,code in cases:
        (usb/'MODE.txt').write_text('CHECK\n')
        p=subprocess.run(['/bin/sh',str(target),'VOLUME'],env=dict(os.environ,**extra),capture_output=True,text=True)
        text=(usb/'HQ10W-RESULT.txt').read_text()
        assert p.returncode==code and message in text,(name,p.returncode,text,p.stderr)
        assert 'MUTATION' not in text+p.stderr and 'REBOOT' not in text+p.stderr
        assert not (root/'forbidden-cache').exists()
        passed.append(name)
    (usb/'MODE.txt').write_text('INSTALL\n');(usb/'HQ10W-INSTALL-REQUESTED.txt').write_text('previous request\n')
    p=subprocess.run(['/bin/sh',str(target),'VOLUME'],capture_output=True,text=True)
    assert p.returncode==0 and 'ALREADY_REQUESTED' in (usb/'HQ10W-RESULT.txt').read_text()
    assert not (root/'forbidden-cache').exists()
    passed.append('repeat install request blocked')
report={'usb_preflight_host_cases':passed,'scope':'simulated CHECK/refusal/repeat-request branches only; no real Recovery request or device write tested'}
output=REPO/'release-work/hq10w-full/usb-guard-checks.json'
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
