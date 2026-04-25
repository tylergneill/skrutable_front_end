#!/usr/bin/env bash
# Tags for tylergneill/skrutable_front_end
# Based on updates.html — one tag per versioned PR merge commit
# Run from the skrutable_front_end repo root

set -e
REPO="$(cd "$(dirname "$0")" && pwd)"

cd "$REPO"
echo "Repo: $(git remote get-url origin)"
echo "Existing tags: $(git tag -l | sort -V | tr '\n' ' ')"
echo ""

# v1.0.0 already exists

git tag v1.4.0 9ce6092c  # PR #14 - added settings page
git tag v1.5.0 850c329e  # PR #15 - added Dharmamitra splitter
git tag v1.6.0 93ccb0b1  # PR #16 - preserve-compound-hyphens
git tag v1.6.1 a2c2fdab  # PR #17 - bumped to lib v1.5.1 (fixed SLP final-char bug)
git tag v1.6.2 d8b38629  # PR #18 - bugfix bump
git tag v1.6.4 8888ff32  # PR #20 - updated splitter import
git tag v1.6.5 9cd50b57  # PR #21 - added 502 handling for oversized Dharmamitra requests
git tag v1.6.6 787f43c0  # PR #22 - cleaned up whole-file splitting
git tag v1.6.7 06003c16  # PR #23 - batching Dharmamitra; extended timeouts
git tag v1.6.8 b3b77cc6  # PR #24 - communicated 2018 splitter outage
git tag v1.6.9 bca8c1b8  # PR #25 - migrated 2018 splitter to Digital Ocean
git tag v1.6.10 334bf178  # PR #26 - updated for new splitter endpoint/format
git tag v1.6.11 07a53355  # PR #27 - improved batching for both splitters
git tag v1.7.0 43ba0272  # PR #29 - added Google Cloud Vision OCR
git tag v1.7.1 b27a4013  # PR #32 - scaled gunicorn/nginx workers and timeouts
git tag v1.7.2 27a517ba  # PR #33 - added favicon
git tag v1.7.3 9ff01049  # PR #34 - fixed two melody player bugs
git tag v1.7.4 433424e8  # PR #35 - improved API, refactored UI with JS
git tag v1.8.0 4f66cfcc  # PR #36 - full redesign, sidebar, dark mode
git tag v1.9.0 1e490c02  # PR #40 - added clear-text and redo buttons
git tag v1.9.1 575e827f  # PR #41 - fixed dark mode colors; guarded melody player
git tag v1.10.0 4e309f58  # PR #43 - auto scheme detection, un-space setting
git tag v1.11.0 e728c1f4  # PR #45 - anunāsika/candrabindu support

echo ""
echo "Tags now: $(git tag -l | sort -V | tr '\n' ' ')"
echo ""
echo "Push with: git -C \"$REPO\" push origin --tags"
