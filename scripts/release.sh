#!/usr/bin/env bash
# Локальный выпуск релиза с Linux. GitHub Actions для тестов не используется.
#
#   scripts/release.sh 0.1.0
#
# Скрипт останавливается, если рабочее дерево грязное, в CHANGELOG.md нет
# раздела версии, не проходят проверки или сборка .deb. Сам по себе он
# создаёт тег v<версия>, пушит его и публикует GitHub Release.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  echo "Использование: scripts/release.sh 0.1.0" >&2
  exit 1
fi
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Версия должна быть вида 0.1.0" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Рабочее дерево не чистое. Закоммитьте или уберите изменения." >&2
  exit 1
fi

if ! grep -qE "^## \\[${VERSION}\\]|^## ${VERSION}( |$)" CHANGELOG.md; then
  echo "В CHANGELOG.md нет раздела версии ${VERSION}." >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "gh не авторизован. Выполните gh auth login и повторите выпуск." >&2
  exit 1
fi

if git rev-parse -q --verify "refs/tags/v${VERSION}" >/dev/null; then
  echo "Тег v${VERSION} уже существует." >&2
  exit 1
fi

echo "Проверки и полный набор тестов"
if command -v just >/dev/null 2>&1; then
  just check
else
  make check
fi
bash scripts/ci_local.sh

echo "Сборка .deb"
bash packaging/build_deb.sh "$VERSION"
DEB="packaging/output/millrepair_${VERSION}_amd64.deb"
if [[ ! -f "$DEB" ]]; then
  echo "Пакет не найден: $DEB" >&2
  exit 1
fi

NOTES="$(mktemp)"
trap 'rm -f "$NOTES"' EXIT
awk -v ver="$VERSION" '
  $0 ~ "^## \\[" ver "\\]" || $0 ~ "^## " ver "( |$)" {flag=1; next}
  /^## / && flag {exit}
  flag {print}
' CHANGELOG.md > "$NOTES"
if [[ ! -s "$NOTES" ]]; then
  prev="$(git describe --tags --abbrev=0 2>/dev/null || true)"
  {
    echo "Изменения с ${prev:-начала истории}."
    echo
    if [[ -n "$prev" ]]; then
      git log --pretty=format:'- %s' "${prev}..HEAD"
    else
      git log --pretty=format:'- %s'
    fi
    echo
  } > "$NOTES"
fi

SUMS="packaging/output/SHA256SUMS.txt"
(
  cd packaging/output
  sha256sum "millrepair_${VERSION}_amd64.deb" > SHA256SUMS.txt
)

git tag -a "v${VERSION}" -m "v${VERSION}"
git push origin "v${VERSION}"
gh release create "v${VERSION}" \
  "$DEB" \
  "$SUMS" \
  --title "v${VERSION}" \
  --notes-file "$NOTES"

echo "Релиз v${VERSION} опубликован. Сборку Windows запускают отдельно: scripts/build_win.ps1 ${VERSION}"
