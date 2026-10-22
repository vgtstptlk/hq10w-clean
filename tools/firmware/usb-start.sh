#!/vendor/bin/sh
# Factory USB entry point. CHECK never requests an installation or reboot.
(
set -eu
export PATH=/system/bin:/system/xbin:/vendor/bin:/product/bin
volume=${1-}
case "$volume" in ''|*[!A-Za-z0-9_-]*) exit 1;; esac
USB=/mnt/media_rw/$volume
main() {
    [ "$(id -u)" = 0 ] || { echo 'STOP: factory root USB context unavailable.'; return 1; }
    mode=$(tr -d '\r\n' < "$USB/MODE.txt")
    case "$mode" in CHECK|INSTALL|ROLLBACK) ;; *) echo 'STOP: MODE.txt must be CHECK, INSTALL or ROLLBACK.'; return 1;; esac
    hook=$(sha256sum /vendor/bin/nl_usb_update.sh | cut -d ' ' -f 1)
    [ "$hook" = 9a220829d35bddaef067f3f76fe320d360af25f5489119e6fd0cb10b2984fbe9 ] || { echo 'STOP: different factory USB mechanism.'; return 1; }
    guard=$(sha256sum "$USB/HQ10W-Full/check-board.sh" | cut -d ' ' -f 1)
    [ "$guard" = @GUARD_SHA256@ ] || { echo 'STOP: board guard damaged.'; return 1; }
    /system/bin/sh "$USB/HQ10W-Full/check-board.sh" || return 1
    date=$(getprop ro.build.date.utc)
    case "$date" in ''|*[!0-9]*) echo 'STOP: build date unavailable.'; return 1;; esac
    [ "$date" -le 1768900794 ] || { echo 'STOP: newer firmware; downgrade refused.'; return 1; }
    # Recovery's OEM fstab expects the first FAT32 USB partition at /sdcard.
    count=$(ls -1 /mnt/media_rw | wc -l | tr -d ' ')
    [ "$count" = 1 ] || { echo 'STOP: keep only one USB/SD volume connected.'; return 1; }
    device=$(awk -v point="$USB" '$2==point {print $1}' /proc/mounts)
    fs=$(awk -v point="$USB" '$2==point {print $3}' /proc/mounts)
    [ "$fs" = vfat ] || { echo 'STOP: FAT32 is required.'; return 1; }
    [ "$(stat -c '%t:%T' "$device")" = 8:1 ] || { echo 'STOP: Recovery expects USB device sda1.'; return 1; }
    file=HQ10W-Clean-Full-1.zip
    expected=@OTA_SHA256@
    if [ "$mode" = ROLLBACK ]; then
        file=HQ10W-Full/factory-V1.0.3.6.zip
        expected=943268ea81004580476cfbf2069c212996d852f5dbc08a3533a6f97f11bfc292
    fi
    actual=$(sha256sum "$USB/$file" | cut -d ' ' -f 1)
    [ "$actual" = "$expected" ] || { echo 'STOP: firmware checksum failed.'; return 1; }
    if [ "$mode" = CHECK ]; then
        echo 'CHECK_OK: exact RX board, layout and complete package verified; nothing installed.'
        return 0
    fi
    [ ! -e "$USB/HQ10W-INSTALL-REQUESTED.txt" ] || { echo 'ALREADY_REQUESTED: no repeated flash. Remove the USB drive.'; return 0; }
    [ ! -s /cache/recovery/command ] || { echo 'STOP: another Recovery command is pending.'; return 1; }
    [ ! -L /cache/recovery ] && [ ! -L /cache/recovery/command ] || { echo 'STOP: unexpected Recovery path.'; return 1; }
    if [ "$mode" = ROLLBACK ]; then
        prep=$(sha256sum "$USB/HQ10W-Full/rollback-prep.sh" | cut -d ' ' -f 1)
        [ "$prep" = @ROLLBACK_PREP_SHA256@ ] || { echo 'STOP: rollback helper damaged.'; return 1; }
        /system/bin/sh "$USB/HQ10W-Full/rollback-prep.sh" || return 1
    elif [ -f /data/local/hq10w-full/profile-v1 ]; then
        # Reinstallation may explicitly re-enable this ROM after an earlier rollback attempt.
        rm -f /data/local/hq10w-full/disabled
        if [ -f /data/local/hq10w-dap/full-rom-v1 ]; then
            rm -f /data/local/hq10w-dap/disabled
        fi
    fi
    # The OTA archive stays on USB.
    mkdir -p /cache/recovery
    printf '%s\n' "--update_package=/sdcard/$file" '--locale=ru_RU' > /cache/recovery/hq10w-command.tmp
    chmod 600 /cache/recovery/hq10w-command.tmp
    chown 0:0 /cache/recovery/hq10w-command.tmp
    restorecon -F /cache/recovery/hq10w-command.tmp
    mv /cache/recovery/hq10w-command.tmp /cache/recovery/command
    echo "$expected" > "$USB/HQ10W-INSTALL-REQUESTED.txt"
    echo 'REBOOTING_TO_RECOVERY: leave USB and power connected until installation completes.'
    sync
    /system/bin/reboot recovery
}
main > "$USB/HQ10W-RESULT.txt" 2>&1
)
