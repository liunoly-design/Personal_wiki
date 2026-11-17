#!/bin/bash
# Run this downloaded file with bash; no sudo, credentials, or app-state copying.
set -euo pipefail

if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo '当前支持 macOS Apple Silicon（M 系列）。' >&2
  exit 1
fi
if ! /usr/bin/xcode-select -p >/dev/null 2>&1; then
  /usr/bin/xcode-select --install
  echo '请完成 macOS 命令行工具安装后，重新运行本脚本。' >&2
  exit 1
fi
brew_bin="$(command -v brew || true)"
if [[ -z "$brew_bin" && -x /opt/homebrew/bin/brew ]]; then brew_bin=/opt/homebrew/bin/brew; fi
if [[ -z "$brew_bin" ]]; then
  echo '请先按 https://brew.sh 安装 Homebrew，然后重新运行本脚本。' >&2
  exit 1
fi
export HOMEBREW_NO_AUTO_UPDATE=1
"$brew_bin" install node@24 python@3.12
node_dir="$("$brew_bin" --prefix node@24)/bin"
python_bin="$("$brew_bin" --prefix python@3.12)/bin/python3.12"
export PATH="$node_dir:$PATH"
if [[ ! -d '/Applications/Google Chrome.app' && ! -d "$HOME/Applications/Google Chrome.app" ]]; then
  "$brew_bin" install --cask google-chrome
fi
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/pwiki-installer.XXXXXX")"
trap 'rm -rf "$work_dir"' EXIT
base_url='https://github.com/liunoly-design/Personal_wiki/releases/latest/download'
/usr/bin/curl --fail --location --proto '=https' --tlsv1.2 "$base_url/pwiki-setup.py" --output "$work_dir/pwiki-setup.py"
/usr/bin/curl --fail --location --proto '=https' --tlsv1.2 "$base_url/pwiki-setup.py.sha256" --output "$work_dir/pwiki-setup.py.sha256"
(cd "$work_dir" && /usr/bin/shasum -a 256 -c pwiki-setup.py.sha256)
"$python_bin" "$work_dir/pwiki-setup.py" install "$@"
