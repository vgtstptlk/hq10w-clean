#!/system/bin/sh
# Runs in stock Recovery BEFORE any partition write, even on an older Android 12 build.
set -eu
export PATH=/system/bin:/system/xbin:/sbin
stop() { echo "HQ10W compatibility: $1" >&2; exit 1; }
[ "$(getprop ro.product.device)" = NL5H00X ] || stop 'device mismatch'
prop() { sed -n "s/^$1=//p" /vendor/build.prop | tr -d '\r'; }
[ "$(prop ro.newlink.projectname)" = YG_5H080_693_RX_ZX ] || stop 'project mismatch'
[ "$(prop ro.board.platform)" = bigfish ] || stop 'platform mismatch'
[ "$(prop ro.vendor.product.cpu.abilist32)" = armeabi-v7a,armeabi ] || stop 'ABI mismatch'
[ "$(prop ro.vendor.build.version.release)" = 12 ] || stop 'Android base mismatch'
# Exact named partition numbers and sizes; the large userdata partition is intentionally not written.
BASE=/dev/block/platform/soc/f9830000.emmc/by-name
check() {
    name=$1; expected=$2; sectors=$3; start=$4
    actual=$(readlink -f "$BASE/$name") || stop 'missing partition'
    [ "$actual" = "/dev/block/$expected" ] || stop 'partition mapping mismatch'
    read -r size < "/sys/class/block/$expected/size"
    [ "$size" = "$sectors" ] || stop 'partition size mismatch'
    read -r position < "/sys/class/block/$expected/start"
    [ "$position" = "$start" ] || stop 'partition position mismatch'
}
check fastboot mmcblk0p1 16384 0
check bootargs mmcblk0p2 2048 16384
check bootargsbak mmcblk0p3 2048 18432
check slaveboot mmcblk0p4 4096 20480
check recovery mmcblk0p5 81920 24576
check tconparam mmcblk0p18 163840 378880
check boot mmcblk0p9 81920 208896
check dtbo mmcblk0p10 2048 290816
check system mmcblk0p20 5120000 550912
check vendor mmcblk0p21 614400 5670912
check atf mmcblk0p11 4096 292864
check misc mmcblk0p15 2048 335872
echo 'HQ10W compatibility: exact RX board layout accepted.'
exit 0
