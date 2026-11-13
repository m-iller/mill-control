#!/usr/bin/env bash
# Сборка millrepair_<версия>_amd64.deb.
#
# На свежем дистрибутиве бинарник может не запуститься на старом из-за glibc,
# поэтому --docker собирает пакет внутри ubuntu:22.04. В GitHub Actions
# используется раннер ubuntu-22.04 и этот же скрипт, без дублирования логики.
#
# Использование:
#   packaging/build_deb.sh 0.1.0
#   packaging/build_deb.sh --docker 0.1.0
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DOCKER=0
VERSION=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --docker)
      DOCKER=1
      shift
      ;;
    *)
      VERSION="$1"
      shift
      ;;
  esac
done

if [[ "$DOCKER" == "1" && -z "${INSIDE_DOCKER:-}" ]]; then
  exec docker run --rm \
    -e INSIDE_DOCKER=1 \
    -v "$ROOT:/src" \
    -w /src \
    ubuntu:22.04 \
    bash -lc "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip binutils lintian && bash packaging/build_deb.sh ${VERSION}"
fi

if [[ -z "$VERSION" ]]; then
  echo "Укажите версию: packaging/build_deb.sh 0.1.0" >&2
  exit 1
fi
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-].*)?$ ]]; then
  echo "Версия должна быть вида 0.1.0, получено: $VERSION" >&2
  exit 1
fi

export SETUPTOOLS_SCM_PRETEND_VERSION="$VERSION"

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[dev]"

rm -rf build dist
.venv/bin/pyinstaller --noconfirm --clean packaging/millrepair.spec

BIN="dist/millrepair/millrepair"
if [[ ! -x "$BIN" ]]; then
  echo "PyInstaller не создал $BIN" >&2
  exit 1
fi

SMOKE_DB="$(mktemp)"
trap 'rm -f "$SMOKE_DB"' EXIT
echo "Проверка бинарника --version"
"$BIN" --version
echo "Проверка бинарника --calc"
"$BIN" --calc --db "$SMOKE_DB"

STAGE="packaging/output/pkg"
rm -rf "$STAGE"
mkdir -p \
  "$STAGE/opt/millrepair" \
  "$STAGE/usr/bin" \
  "$STAGE/usr/share/applications" \
  "$STAGE/usr/share/icons/hicolor/256x256/apps" \
  "$STAGE/DEBIAN"

cp -a dist/millrepair/. "$STAGE/opt/millrepair/"
# Загружаемые библиотеки не должны быть исполняемыми: иначе lintian считает это ошибкой.
find "$STAGE/opt/millrepair" -type f \( -name '*.so' -o -name '*.so.*' \) -exec chmod 644 {} +
cat > "$STAGE/usr/bin/millrepair" <<'EOF'
#!/bin/sh
exec /opt/millrepair/millrepair "$@"
EOF
chmod 755 "$STAGE/usr/bin/millrepair" "$STAGE/opt/millrepair/millrepair"
cp packaging/linux/millrepair.desktop "$STAGE/usr/share/applications/millrepair.desktop"
cp packaging/icons/millrepair.png "$STAGE/usr/share/icons/hicolor/256x256/apps/millrepair.png"
sed "s/@VERSION@/${VERSION}/" packaging/linux/control.template > "$STAGE/DEBIAN/control"

mkdir -p "$STAGE/usr/share/doc/millrepair" "$STAGE/usr/share/lintian/overrides"
cp packaging/linux/lintian-overrides "$STAGE/usr/share/lintian/overrides/millrepair"
cat > "$STAGE/usr/share/doc/millrepair/copyright" <<'EOF'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: millrepair
Upstream-Contact: Mill Repair Window <packaging@millrepair.dev>

Files: *
Copyright: 2026 Mill Repair Window
License: MIT
 Permission is hereby granted, free of charge, to any person obtaining a copy
 of this software to deal in the Software without restriction, including
 without limitation the rights to use, copy, modify, merge, publish, distribute,
 sublicense, and/or sell copies of the Software.
EOF
CHANGELOG_ENTRY="millrepair (${VERSION}) unstable; urgency=medium

  * Выпуск ${VERSION}.

 -- Mill Repair Window <packaging@millrepair.dev>  $(date -R)"
printf '%s\n' "$CHANGELOG_ENTRY" | gzip -n -9 > "$STAGE/usr/share/doc/millrepair/changelog.gz"

mkdir -p packaging/output
DEB="packaging/output/millrepair_${VERSION}_amd64.deb"
dpkg-deb --build --root-owner-group "$STAGE" "$DEB"
echo "Содержимое control:"
dpkg-deb --info "$DEB"

if command -v lintian >/dev/null 2>&1; then
  echo "lintian (ошибки недопустимы, предупреждения можно):"
  lintian --fail-on error "$DEB"
else
  echo "lintian не установлен, проверка пакета ограничена dpkg-deb --info" >&2
fi

echo "Собран $DEB"
