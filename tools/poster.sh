#!/bin/sh
# Make scenes/<SCENE>/poster.jpg (noon) and poster-dark.jpg (23:00), scenery only (`still` values),
# from headless runs. SIZE=<your monitor> makes the overview line up exactly. Env: SCENE, SIZE, SHOT.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
scene=${SCENE:-fishtank} size=${SIZE:-3440x1440} shot=${SHOT:-10}
case $shot in *[!0-9]*|'') echo 'bad SHOT' >&2; exit 1;; esac
dst="$here/scenes/$scene"
[ -d "$dst" ] || { echo "no scene $scene" >&2; exit 1; }
tmp=$(mktemp -d)
# An old poster would be the wallpaper under the new shot, so park it; it comes back unless the run succeeds.
mkdir "$tmp/old"
for f in "$dst"/poster*.jpg; do if [ -e "$f" ]; then mv "$f" "$tmp/old/"; fi; done
trap 'mv "$tmp"/old/* "$dst/" 2>/dev/null || true; rm -rf "$tmp"' EXIT
for name in poster:12 poster-dark:23; do
    OUT="$tmp/${name%:*}" SCENE=$scene SIZE=$size HOUR=${name#*:} POSTER=1 SHOT=$shot \
        "$here/dev.sh" --headless "$((shot + 3))" > /dev/null
    png="$tmp/${name%:*}/s0.png" jpg="$tmp/${name%:*}.jpg"
    [ -s "$png" ] || { echo "no screenshot for ${name%:*}, see $tmp/${name%:*}/log" >&2
        mv "$tmp"/old/* "$dst/" 2>/dev/null || true; trap - EXIT; exit 1; }
    timeout -k 5 30 gjs -c 'imports.gi.GdkPixbuf.Pixbuf.new_from_file(ARGV[0]).savev(ARGV[1], "jpeg", ["quality"], ["90"])' "$png" "$jpg"
done
rm -rf "$tmp/old"
mv "$tmp/poster.jpg" "$tmp/poster-dark.jpg" "$dst/"
ls -l "$dst"/poster*.jpg
