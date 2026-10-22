#!/usr/bin/env python3
"""Evaluate the exact guard against recorded factory props/layout, entirely on the host."""
from pathlib import Path
import json
import os
import re
import subprocess
import tempfile

REPO=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
FIXTURES=HERE/'fixtures'
fixture=json.loads((FIXTURES/'hardware-layout.json').read_text())
layout=fixture['layout'];links=fixture['links']
passed=[]
with tempfile.TemporaryDirectory(prefix='hq10w-full-guard-') as folder:
    temp=Path(folder)
    for part,fields in layout.items():
        (temp/part).mkdir()
        for name,value in fields.items(): (temp/part/name).write_text(value+'\n')
    envfile=temp/'mock.sh'
    envfile.write_text('getprop() { echo NL5H00X; }\nreadlink() { case "$2" in\n'+
        ''.join(f'*/{name}) echo /dev/block/{target};;\n' for name,target in links.items())+
        '*) return 1;; esac; }\n')
    script=(HERE/'check-board.sh').read_text().replace('export PATH=/system/bin:/system/xbin:/sbin','. "'+str(envfile)+'"')
    script=script.replace('/vendor/build.prop',str(temp/'build.prop')).replace('/sys/class/block/',str(temp)+'/')
    target=temp/'check.sh';target.write_text(script)
    for source in ('old-vendor.prop','base-vendor.prop'):
        props=(FIXTURES/source).read_text()
        (temp/'build.prop').write_text(props)
        p=subprocess.run(['/bin/sh',str(target)],capture_output=True,text=True)
        assert p.returncode==0,(source,p.stdout,p.stderr)
        passed.append(source+' factory properties accepted')
    cases=[('different project',lambda: (temp/'build.prop').write_text(props.replace('YG_5H080_693_RX_ZX','YG_5H080_693_ZX'))),
           ('different system size',lambda: (temp/'mmcblk0p20/size').write_text('5000000\n')),
           ('different system position',lambda: (temp/'mmcblk0p20/start').write_text('550913\n'))]
    for name,change in cases:
        (temp/'build.prop').write_text(props)
        for field,value in layout['mmcblk0p20'].items(): (temp/'mmcblk0p20'/field).write_text(value+'\n')
        change()
        p=subprocess.run(['/bin/sh',str(target)],capture_output=True,text=True)
        assert p.returncode!=0,(name,p.stdout,p.stderr)
        passed.append(name+' rejected')
    # Critical mapping fixture independently confirms the exact labels used by the stock OTA.
    assert links['boot']=='mmcblk0p9' and links['tconparam']=='mmcblk0p18' and links['atf']=='mmcblk0p11'
for path in HERE.glob('*.sh'):
    subprocess.run(['/bin/sh','-n',str(path)],check=True)
report={'board_guard_host_cases':passed,'scope':'recorded old/new factory properties and recorded hardware layout; no Recovery execution or flashing'}
output=REPO/'release-work/hq10w-full/guard-checks.json'
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
