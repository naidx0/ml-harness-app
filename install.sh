#!/bin/sh
# ML Harness for macOS, installed with one line in Terminal:
#
#   curl -fsSL https://raw.githubusercontent.com/naidx0/ml-harness-app/main/install.sh | sh
#
# What it does, in order. It is safe to run again: anything already done is skipped.
#
#   1. Downloads the latest ML Harness .dmg for this Mac (Apple Silicon or Intel)
#      and checks its SHA-256 against the release's SHA256SUMS.txt. A mismatch
#      stops everything. Skipped when that version is already installed.
#   2. Copies ML Harness.app into /Applications (or ~/Applications when
#      /Applications is not writable). No sudo.
#   3. Installs Ollama (the signed app from ollama.com) when no Ollama is found,
#      and starts it.
#   4. Pulls one local model when it is not pulled yet (qwen3.5:4b, about 3.4 GB).
#   5. Opens ML Harness and connects that model, so the first screen is ready
#      for a question.
#
# Options, set before the line, for example:
#
#   curl -fsSL https://raw.githubusercontent.com/naidx0/ml-harness-app/main/install.sh | MLH_MODEL=qwen3.5:2b sh
#
#   MLH_MODEL       which Ollama model to pull and connect (default qwen3.5:4b)
#   MLH_NO_OLLAMA   1 = install only the app; you will connect an API key instead
#   MLH_NO_LAUNCH   1 = do not open the app at the end
#   MLH_VERSION     a release tag such as v0.1.1 (default: the latest release)
#   MLH_DMG         a local .dmg to install instead of downloading one (testing)

set -eu

REPO="naidx0/ml-harness-app"
MODEL="${MLH_MODEL:-qwen3.5:4b}"
OLLAMA_URL="http://127.0.0.1:11434"
DATA_ROOT="${MLH_DATA_ROOT:-$HOME/.local/share/ml-harness}"
STARTED=$(date +%s)
WORK=$(mktemp -d "${TMPDIR:-/tmp}/ml-harness-install.XXXXXX")
MOUNT=""

say() { printf '>>> %s\n' "$1"; }
note() { printf '    %s\n' "$1"; }
fail() {
  printf '\nStopped: %s\n' "$1" >&2
  printf 'Run the line again after fixing that, or download the .dmg from https://github.com/%s/releases/latest\n' "$REPO" >&2
  exit 1
}
cleanup() {
  if [ -n "$MOUNT" ]; then hdiutil detach "$MOUNT" -quiet >/dev/null 2>&1 || true; fi
  rm -rf "$WORK"
}
trap cleanup EXIT

[ "$(uname -s)" = "Darwin" ] || fail "this line is for macOS. On Windows, use install.ps1 (see the README)."

case "$(uname -m)" in
  arm64) ARCH="arm64" ;;
  x86_64) ARCH="x64" ;;
  *) fail "this Mac's processor ($(uname -m)) has no build." ;;
esac

# ---- 1. which release --------------------------------------------------------
if [ -n "${MLH_VERSION:-}" ]; then
  API="https://api.github.com/repos/$REPO/releases/tags/$MLH_VERSION"
else
  API="https://api.github.com/repos/$REPO/releases/latest"
fi
APP=""
for dir in /Applications "$HOME/Applications"; do
  if [ -d "$dir/ML Harness.app" ]; then APP="$dir/ML Harness.app"; fi
done

if [ -n "${MLH_DMG:-}" ]; then
  say "Installing the local file $MLH_DMG"
  DMG="$MLH_DMG"
  WANT=""
else
  say "Finding the latest ML Harness release"
  curl -fsSL -H "User-Agent: ml-harness-install" "$API" -o "$WORK/release.json" ||
    fail "could not read $API. Check the internet connection."
  TAG=$(sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' "$WORK/release.json" | head -n 1)
  WANT=${TAG#v}
  DMG_URL=$(sed -n 's/.*"browser_download_url": *"\([^"]*\)".*/\1/p' "$WORK/release.json" | grep -E "macos-$ARCH\.dmg$" | head -n 1 || true)
  SUMS_URL=$(sed -n 's/.*"browser_download_url": *"\([^"]*SHA256SUMS\.txt\)".*/\1/p' "$WORK/release.json" | head -n 1)
  [ -n "$DMG_URL" ] || fail "release $TAG has no macOS ($ARCH) download yet."
  [ -n "$SUMS_URL" ] || fail "release $TAG has no SHA256SUMS.txt, so the download cannot be checked."
  DMG=""
fi

HAVE=""
if [ -n "$APP" ]; then
  HAVE=$(defaults read "$APP/Contents/Info" CFBundleShortVersionString 2>/dev/null || true)
fi

# ---- 3a. Ollama, started first because it is the big download ----------------
find_ollama() {
  if command -v ollama >/dev/null 2>&1; then command -v ollama; return; fi
  for candidate in /Applications/Ollama.app/Contents/Resources/ollama "$HOME/Applications/Ollama.app/Contents/Resources/ollama"; do
    if [ -x "$candidate" ]; then echo "$candidate"; return; fi
  done
}
OLLAMA_PID=""
if [ "${MLH_NO_OLLAMA:-}" != "1" ] && [ -z "$(find_ollama)" ]; then
  say "Ollama was not found. Downloading it from ollama.com (about 200 MB), in the background"
  ( curl -fsSL -o "$WORK/Ollama-darwin.zip" "https://ollama.com/download/Ollama-darwin.zip" ) &
  OLLAMA_PID=$!
fi

# ---- 1b and 2. the app, unless this version is already installed -------------
if [ -n "$APP" ] && [ -n "$WANT" ] && [ "$HAVE" = "$WANT" ]; then
  say "ML Harness $WANT is already installed"
else
  if [ -z "$DMG" ]; then
    NAME=$(basename "$DMG_URL")
    say "Downloading $NAME"
    DMG="$WORK/$NAME"
    curl -fsSL -o "$DMG" "$DMG_URL" || fail "the download of $NAME failed."
    curl -fsSL -o "$WORK/SHA256SUMS.txt" "$SUMS_URL" || fail "SHA256SUMS.txt could not be downloaded."
    EXPECTED=$(grep " $NAME\$" "$WORK/SHA256SUMS.txt" | awk '{print $1}' | head -n 1 | tr 'A-F' 'a-f')
    [ -n "$EXPECTED" ] || fail "SHA256SUMS.txt does not list $NAME."
    ACTUAL=$(shasum -a 256 "$DMG" | awk '{print $1}')
    [ "$EXPECTED" = "$ACTUAL" ] || fail "the download's SHA-256 is $ACTUAL but the release says $EXPECTED. Nothing was installed."
    note "SHA-256 matches the release: $ACTUAL"
  fi
  if pgrep -f "ML Harness.app/Contents/MacOS" >/dev/null 2>&1; then
    fail "an older ML Harness is open. Quit it, then run the line again."
  fi
  say "Installing ML Harness"
  MOUNT="$WORK/mount"
  mkdir -p "$MOUNT"
  hdiutil attach "$DMG" -nobrowse -readonly -quiet -mountpoint "$MOUNT" || fail "the .dmg would not open."
  [ -d "$MOUNT/ML Harness.app" ] || fail "the .dmg has no ML Harness.app in it."
  TARGET_DIR="/Applications"
  [ -w "$TARGET_DIR" ] || { TARGET_DIR="$HOME/Applications"; mkdir -p "$TARGET_DIR"; }
  rm -rf "$TARGET_DIR/ML Harness.app"
  ditto "$MOUNT/ML Harness.app" "$TARGET_DIR/ML Harness.app"
  hdiutil detach "$MOUNT" -quiet >/dev/null 2>&1 || true
  MOUNT=""
  APP="$TARGET_DIR/ML Harness.app"
  # A file curl downloaded carries no quarantine flag; clearing it anyway
  # covers a .dmg that came from a browser (MLH_DMG).
  xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
  note "Installed: $APP"
fi

ollama_up() { curl -fs -m 3 "$OLLAMA_URL/api/version" >/dev/null 2>&1; }

if [ "${MLH_NO_OLLAMA:-}" != "1" ]; then
  # ---- 3b. Ollama installed and answering ------------------------------------
  if [ -n "$OLLAMA_PID" ]; then
    say "Waiting for the Ollama download to finish"
    wait "$OLLAMA_PID" || fail "the Ollama download failed. ML Harness is installed; connect an API key in the app, or install Ollama from https://ollama.com/download and run this line again."
    OLLAMA_DIR="/Applications"
    [ -w "$OLLAMA_DIR" ] || { OLLAMA_DIR="$HOME/Applications"; mkdir -p "$OLLAMA_DIR"; }
    ditto -x -k "$WORK/Ollama-darwin.zip" "$OLLAMA_DIR" || fail "the Ollama download would not unzip."
    note "Ollama installed: $OLLAMA_DIR/Ollama.app"
  fi
  OLLAMA=$(find_ollama)
  [ -n "$OLLAMA" ] || fail "Ollama is not where it was put. Install it from https://ollama.com/download and run this line again."
  if ! ollama_up; then
    say "Starting Ollama"
    if [ -d "/Applications/Ollama.app" ] || [ -d "$HOME/Applications/Ollama.app" ]; then
      open -g -a Ollama 2>/dev/null || ("$OLLAMA" serve >/dev/null 2>&1 &)
    else
      ("$OLLAMA" serve >/dev/null 2>&1 &)
    fi
    i=0
    while ! ollama_up && [ $i -lt 45 ]; do sleep 2; i=$((i + 1)); done
    ollama_up || fail "Ollama is installed but did not answer on $OLLAMA_URL within 90 s. Open Ollama from Applications and run this line again."
  fi

  # ---- 4. the model ------------------------------------------------------------
  case "$MODEL" in *:*) WANTED="$MODEL" ;; *) WANTED="$MODEL:latest" ;; esac
  if curl -fs "$OLLAMA_URL/api/tags" | grep -q "\"name\":\"$WANTED\""; then
    say "The model $MODEL is already pulled"
  else
    say "Pulling the model $MODEL (a few GB; Ollama shows its progress)"
    "$OLLAMA" pull "$MODEL" || fail "ollama pull $MODEL failed. ML Harness and Ollama are installed; run the line again to retry the pull."
  fi
fi

if [ "${MLH_NO_LAUNCH:-}" = "1" ]; then
  say "Done in $(( $(date +%s) - STARTED )) s. Open ML Harness from Applications."
  exit 0
fi

# ---- 5. open it and connect the model ----------------------------------------
say "Opening ML Harness (the first launch sets up its own Python, so it needs internet)"
open "$APP"
ENGINE_FILE="$DATA_ROOT/engine.json"
BASE=""
TOKEN=""
i=0
while [ $i -lt 300 ]; do
  if [ -f "$ENGINE_FILE" ]; then
    BASE=$(sed -n 's/.*"base_url": *"\([^"]*\)".*/\1/p' "$ENGINE_FILE" | head -n 1)
    TOKEN=$(sed -n 's/.*"token": *"\([^"]*\)".*/\1/p' "$ENGINE_FILE" | head -n 1)
    if [ -n "$BASE" ] && curl -fs -m 3 "$BASE/health" >/dev/null 2>&1; then break; fi
  fi
  BASE=""
  sleep 2
  i=$((i + 1))
done
if [ -z "$BASE" ]; then
  say "ML Harness is open, but its engine did not answer within 10 minutes, so the model was not connected for you."
  note 'In the app, click New chat, then "Use a model on this computer".'
  exit 0
fi

if [ "${MLH_NO_OLLAMA:-}" != "1" ]; then
  # The same three calls the app's one-click connect makes: reuse the row for
  # this model if there is one, otherwise create it; then make it active and probe it.
  AUTH="Authorization: Bearer $TOKEN"
  ROWS=$(curl -fs -H "$AUTH" "$BASE/api/providers" || true)
  ID=$(printf '%s' "$ROWS" | tr '{' '\n' | grep "\"model\": *\"$MODEL\"" | grep '"adapter": *"ollama"' | sed -n 's/.*"id": *\([0-9][0-9]*\).*/\1/p' | head -n 1)
  if [ -z "$ID" ]; then
    BODY=$(printf '{"name":"%s","base_url":"%s","model":"%s","adapter":"ollama"}' "$MODEL" "$OLLAMA_URL" "$MODEL")
    ID=$(curl -fs -H "$AUTH" -H "Content-Type: application/json" -d "$BODY" "$BASE/api/providers" | grep -o '"id": *[0-9][0-9]*' | head -n 1 | grep -o '[0-9][0-9]*$')
  fi
  if [ -n "$ID" ] &&
    curl -fs -X POST -H "$AUTH" "$BASE/api/providers/$ID/activate" >/dev/null &&
    curl -fs -m 300 -X POST -H "$AUTH" "$BASE/api/providers/$ID/probe" >/dev/null; then
    note "Connected $MODEL"
  else
    note "The model is pulled, but connecting it failed."
    note 'In the app, click New chat, then "Use a model on this computer".'
  fi
fi

printf '\n'
say "Done in $(( $(date +%s) - STARTED )) s. ML Harness is open. Type what you want in the box, for example:"
note "Train a logistic regression on scikit-learn's iris dataset with an 80/20 split and tell me the test accuracy."
if [ "${MLH_NO_OLLAMA:-}" = "1" ]; then note 'No local model was set up. Click New chat, then "Use an API key".'; fi
