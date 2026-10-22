#!/vendor/bin/sh
# Run before class_start main; preserve the OEM initialization and factory Home fallback.
export PATH=/system/bin:/vendor/bin
[ -f /data/local/hq10w-full/disabled ] && exit 0
apk=/system/app/CleanTVHome/CleanTVHome.apk
[ -f "$apk" ] || exit 0
actual=$(sha256sum "$apk" | cut -d ' ' -f 1)
[ "$actual" = @HOME_SHA256@ ] || exit 0
setprop vendor.newlink.launcher.package com.gathin.tvhome
exit 0
