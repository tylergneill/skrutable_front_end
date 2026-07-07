#!/usr/bin/env bash
# Usage: ./split_meld.sh
#
# Reads from screenshots/raw/, screenshots/norm_dandas/, and screenshots/norm_ws/,
# writes crops to splits/raw/, splits/norm_dandas/, and splits/norm_ws/.
#
# GCV meld layout:    [GCV OCR | ground truth]
# Sarvam meld layout: [ground truth | sarvam OCR]
#
# Output files per variant:
#   gcv_N_right.png          — GCV OCR output (left half of GCV meld)
#   gt_vs_gcv_N_left.png     — ground truth diff vs GCV (right half of GCV meld)
#   gt_vs_sarvam_N_left.png  — ground truth diff vs Sarvam (left half of Sarvam meld)
#   sarvam_N_right.png       — Sarvam OCR output (right half of Sarvam meld)

set -euo pipefail
MELD="$(cd "$(dirname "$0")" && pwd)"

split_dir() {
    local src_dir="$1"
    local out_dir="$2"
    mkdir -p "$out_dir"

    for src in "$src_dir"/gcv_[0-9]*.png; do
        local base; base="$(basename "$src")"
        local p="${base#gcv_}"; p="${p%.png}"
        local w h half
        w=$(magick identify -format "%w" "$src")
        h=$(magick identify -format "%h" "$src")
        half=$((w / 2))
        magick "$src" -crop "${half}x${h}+0+0"       +repage "$out_dir/gcv_${p}_right.png"
        magick "$src" -crop "${half}x${h}+${half}+0" +repage "$out_dir/gt_vs_gcv_${p}_left.png"
        echo "gcv_${p}: split at ${half}x${h} -> $(basename "$out_dir")"
    done

    for src in "$src_dir"/sarvam_[0-9]*.png; do
        local base; base="$(basename "$src")"
        local p="${base#sarvam_}"; p="${p%.png}"
        local w h half
        w=$(magick identify -format "%w" "$src")
        h=$(magick identify -format "%h" "$src")
        half=$((w / 2))
        magick "$src" -crop "${half}x${h}+0+0"       +repage "$out_dir/gt_vs_sarvam_${p}_left.png"
        magick "$src" -crop "${half}x${h}+${half}+0" +repage "$out_dir/sarvam_${p}_right.png"
        echo "sarvam_${p}: split at ${half}x${h} -> $(basename "$out_dir")"
    done
}

split_dir "$MELD/screenshots/raw"        "$MELD/splits/raw"
split_dir "$MELD/screenshots/norm_dandas" "$MELD/splits/norm_dandas"
split_dir "$MELD/screenshots/norm_ws"    "$MELD/splits/norm_ws"
