#!/usr/bin/env bash
# End-to-end test of the zollo.azuregos collection against a running API with
# an empty database: the modules, then the configure role (twice: the second
# run must change nothing), then export -> configure round trip.
#
#   AZUREGOS_URL=http://localhost:8000 AZUREGOS_USERNAME=admin@... AZUREGOS_PASSWORD=... \
#     ansible/tests/run-e2e.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
export ANSIBLE_COLLECTIONS_PATH="$here/../"
export ANSIBLE_FORCE_COLOR=0 ANSIBLE_NOCOLOR=1 ANSIBLE_DEPRECATION_WARNINGS=0
: "${AZUREGOS_URL:?}" "${AZUREGOS_USERNAME:?}" "${AZUREGOS_PASSWORD:?}"
auth=(-e "azuregos_url=$AZUREGOS_URL" -e "azuregos_username=$AZUREGOS_USERNAME"
      -e "azuregos_password=$AZUREGOS_PASSWORD")
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

expect_changed() {  # <log> <n>: the play recap must report exactly n changes
  local got
  got="$(grep -Eo 'changed=[0-9]+' "$1" | tail -1 | cut -d= -f2)"
  if [ "$got" != "$2" ]; then
    echo "expected changed=$2 in $1, got changed=$got" >&2
    exit 1
  fi
}

echo "== modules"
ansible-playbook "$here/e2e/modules.yml"

echo "== configure role: check mode on an empty instance"
ansible-playbook zollo.azuregos.configure "${auth[@]}" -e "@$here/e2e/config.yml" --check --diff

echo "== configure role: apply"
ansible-playbook zollo.azuregos.configure "${auth[@]}" -e "@$here/e2e/config.yml" | tee "$work/1.log"

echo "== configure role: apply again (must be a no-op)"
ansible-playbook zollo.azuregos.configure "${auth[@]}" -e "@$here/e2e/config.yml" | tee "$work/2.log"
expect_changed "$work/2.log" 0

echo "== export, then apply the export (must be a no-op)"
ansible-playbook zollo.azuregos.export "${auth[@]}" -e "azuregos_export_path=$work/export.yml"
cat "$work/export.yml"
grep -q 'category: Hardware' "$work/export.yml"
grep -q -- '- Request access' "$work/export.yml"
ansible-playbook zollo.azuregos.configure "${auth[@]}" -e "@$work/export.yml" | tee "$work/3.log"
expect_changed "$work/3.log" 0
echo "e2e OK"
