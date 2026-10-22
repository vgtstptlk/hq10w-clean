#!/vendor/bin/sh
# Optional late-boot customization; Android and the factory boot wrapper remain independent.
set -eu
export PATH=/system/bin:/system/xbin:/vendor/bin:/product/bin
STATE=/data/local/hq10w-full
AUDIO=/data/local/hq10w-dap
SOURCE=/vendor/etc/hq10w-clean/audio
[ -f "$STATE/disabled" ] && exit 0
[ "$(getprop ro.newlink.projectname)" = YG_5H080_693_RX_ZX ] || exit 0
[ "$(getprop ro.build.fingerprint)" = 'HiDPT/Hi3751V553_32_DMO_2layer_1024M/Hi3751V553:12/SP1A.210812.016/hehq01201719:userdebug/dev-keys' ] || exit 0
[ ! -L "$STATE" ] && [ ! -L "$AUDIO" ] || exit 0
mkdir -p "$STATE"
chmod 700 "$STATE"
# Apply the proven privacy profile once per recipient data installation, preserving later choices.
if [ ! -f "$STATE/profile-v1" ]; then
    pm disable --user 0 com.newlink.service/com.newlink.service.service.DataUploadService
    pm disable --user 0 com.zeasn.whale.saas/com.zeasn.tou_library.web.receiver.NetWorkStateReceiver
    pm disable-user --user 0 zeasn.open.technical.tv.store
    am stopservice -n com.newlink.service/.service.DataUploadService >/dev/null 2>&1 || :
    am force-stop zeasn.open.technical.tv.store
    setprop persist.sys.logcat.enable false
    touch "$STATE/profile-v1"
fi
# An existing audio customization is never overwritten. Recognized completed stages are reused.
if [ -e "$AUDIO" ]; then
    [ -f "$AUDIO/full-rom-v1" ] || exit 0
else
    stage=$STATE/audio-stage
    # This directory is owned exclusively by this ROM, and contains no recipient app data.
    rm -rf "$stage"
    mkdir -p "$stage/soundfx"
    chmod 755 "$stage" "$stage/soundfx"
    cp -p /vendor/lib/soundfx/*.so "$stage/soundfx/"
    cp "$SOURCE/libdlbatmos.so" "$SOURCE/libhqvirtualbass.so" "$stage/soundfx/"
    for name in startup.sh healthy.sh watchdog.sh restore.sh audio_effects.conf speaker-control.jar; do
        cp "$SOURCE/$name" "$stage/$name"
    done
    chmod 700 "$stage/"*.sh
    chmod 644 "$stage/soundfx/"*.so "$stage/audio_effects.conf" "$stage/speaker-control.jar"
    chcon -R u:object_r:vendor_file:s0 "$stage/soundfx"
    chcon u:object_r:vendor_configs_file:s0 "$stage/audio_effects.conf"
    touch "$stage/full-rom-v1"
    mv "$stage" "$AUDIO"
fi
# A prior failed startup deliberately leaves disabled in place; do not reset it on every boot.
[ -f "$AUDIO/disabled" ] && exit 0
setsid /system/bin/sh "$AUDIO/startup.sh" > "$AUDIO/boot.log" 2>&1 < /dev/null &
exit 0
