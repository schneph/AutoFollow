#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
#
# Attach installers to the GitHub release for a tag, creating the release if no
# build has yet. Several OS builds run at once, so a lost create race falls
# through to the upload.
#
#   bash scripts/publish-release-asset.sh <tag> <file>...
set -euo pipefail

tag="$1"
shift
repo="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is not set}"

if ! gh release view "$tag" -R "$repo" >/dev/null 2>&1; then
  gh release create "$tag" -R "$repo" --title "AutoFollow ${tag}" --generate-notes || true
fi
gh release upload "$tag" "$@" --clobber -R "$repo"
