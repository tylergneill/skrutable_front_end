#!/usr/bin/env bash
# Usage: ./split_screenshots.sh
#
# Traverses BASE/<base_text>/<provider_date>/meld_screenshots/{as_left,as_right}/{raw,normalized}/
# and writes crops to the sibling meld_splits/{as_left,as_right}/{raw,normalized}/ directory.
#
# as_left layout:  [OCR | ground truth diff]  — used when this run is in the left column
# as_right layout: [ground truth diff | OCR]  — used when this run is in the right column
#
# Input files: NNN.png (e.g. 005.png, 006.png …)
# Output files per side/variant:
#   ocr_NNN.png      — the OCR panel half
#   gt_diff_NNN.png  — the ground truth diff panel half

set -euo pipefail
BASE="$(cd "$(dirname "$0")" && pwd)"

split_dir() {
    local src_dir="$1"
    local out_dir="$2"
    local side="$3"   # "as_left" or "as_right"
    mkdir -p "$out_dir"

    for src in "$src_dir"/[0-9]*.png; do
        [ -e "$src" ] || continue
        local base; base="$(basename "$src")"
        local p="${base%.png}"
        local w h half
        w=$(magick identify -format "%w" "$src")
        h=$(magick identify -format "%h" "$src")
        half=$((w / 2))

        if [ "$side" = "as_left" ]; then
            # meld layout: [OCR | ground truth diff]
            magick "$src" -crop "${half}x${h}+0+0"       +repage "$out_dir/ocr_${p}.png"
            magick "$src" -crop "${half}x${h}+${half}+0" +repage "$out_dir/gt_diff_${p}.png"
        else
            # meld layout: [ground truth diff | OCR]
            magick "$src" -crop "${half}x${h}+0+0"       +repage "$out_dir/gt_diff_${p}.png"
            magick "$src" -crop "${half}x${h}+${half}+0" +repage "$out_dir/ocr_${p}.png"
        fi
        echo "${side} ${p}: split at ${half}x${h} -> $(basename "$out_dir")"
    done
}

for bt_dir in "$BASE"/*/; do
    [ -d "$bt_dir" ] || continue
    bt_name="$(basename "$bt_dir")"
    [ "$bt_name" = "." ] && continue

    for prov_dir in "$bt_dir"*/; do
        [ -d "$prov_dir" ] || continue
        meld_src="$prov_dir/meld_screenshots"
        [ -d "$meld_src" ] || continue

        for side in as_left as_right; do
            side_src="$meld_src/$side"
            [ -d "$side_src" ] || continue
            for variant in raw normalized; do
                src_subdir="$side_src/$variant"
                out_subdir="$prov_dir/meld_splits/$side/$variant"
                [ -d "$src_subdir" ] || continue
                split_dir "$src_subdir" "$out_subdir" "$side"
            done
        done
    done
done
