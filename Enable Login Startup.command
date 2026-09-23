#!/bin/zsh
cd "${0:A:h}" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v python3 >/dev/null; then
  print "Install Python and FFmpeg first; see docs/MAC.md."
  read '?Press Return to close.'
  exit 1
fi
python3 -X utf8 ./manage.py enable-login
result=$?
if (( result != 0 )); then
  read '?Press Return to close.'
fi
exit $result
