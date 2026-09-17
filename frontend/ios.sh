#!/bin/zsh

set -euo pipefail

script_dir="${0:A:h}"
bundled_dependencies="${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies"

if ! command -v pnpm >/dev/null 2>&1 || ! command -v node >/dev/null 2>&1; then
  if [[ -x "${bundled_dependencies}/node/bin/node" && -x "${bundled_dependencies}/bin/fallback/pnpm" ]]; then
    export PATH="${bundled_dependencies}/node/bin:${bundled_dependencies}/bin/fallback:${PATH}"
  else
    print -u2 "Node and pnpm were not found. Install Node.js 20+ first, then run: corepack enable"
    exit 1
  fi
fi

cd "${script_dir}"

case "${1:-device}" in
  device)
    pnpm ios:device
    pnpm exec cap open ios
    ;;
  release)
    pnpm ios:release
    pnpm exec cap open ios
    ;;
  simulator)
    pnpm ios:open
    ;;
  sync)
    pnpm ios:sync
    ;;
  *)
    print -u2 "Usage: ./ios.sh [device|release|simulator|sync]"
    exit 2
    ;;
esac
