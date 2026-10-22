#!/system/bin/sh
# Restore factory component/audio defaults on the recipient, then let the unchanged OEM OTA run.
set -eu
export PATH=/system/bin:/system/xbin:/vendor/bin:/product/bin
STATE=/data/local/hq10w-full
AUDIO=/data/local/hq10w-dap
[ "$(id -u)" = 0 ] || exit 1
[ ! -L "$STATE" ] && [ ! -L "$AUDIO" ] || exit 1
[ -f "$STATE/profile-v1" ] || exit 0
# This is a return to factory defaults, not a snapshot of the recipient's former preferences.
touch "$STATE/disabled"
if [ -f "$AUDIO/full-rom-v1" ]; then
    actual=$(sha256sum "$AUDIO/restore.sh" | cut -d ' ' -f 1)
    [ "$actual" = @RESTORE_SHA256@ ] || { echo 'STOP: audio rollback helper changed.'; exit 1; }
    /system/bin/sh "$AUDIO/restore.sh"
fi
for target in com.newlink.service/com.newlink.service.service.DataUploadService com.zeasn.whale.saas/com.zeasn.tou_library.web.receiver.NetWorkStateReceiver zeasn.open.technical.tv.store; do
    pm default-state --user 0 "$target"
done
setprop persist.sys.logcat.enable true
setprop vendor.newlink.launcher.package com.zeasn.whale.saas
echo 'Factory component/audio defaults selected.'
