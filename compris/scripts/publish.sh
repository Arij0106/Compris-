#!/usr/bin/env bash
# Publie le dépôt sur GitHub après vérification des secrets.
# Usage : ./scripts/publish.sh https://github.com/<utilisateur>/<repo>.git
set -euo pipefail
REMOTE="${1:?Usage: $0 <url-du-remote-github>}"

if [ -f backend/.env ] && ! git check-ignore -q backend/.env; then
  echo "backend/.env n’est pas ignoré : abandon"; exit 1
fi

[ -d .git ] || git init -b main
git add .
if git ls-files | grep -E "(^|/)\.env$"; then
  echo "Un fichier .env est suivi par Git : abandon"; exit 1
fi
if git grep --cached -nE "gsk_[A-Za-z0-9]{20,}|xai-[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{30,}"; then
  echo "Clé API détectée : abandon"; exit 1
fi

git commit -m "feat: initial submission" || true
git remote add origin "$REMOTE" 2>/dev/null || git remote set-url origin "$REMOTE"
git push -u origin main
