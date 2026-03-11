#!/usr/bin/env bash
# Pre-flight checks for production deployment.
# Run before starting services with docker-compose.prod.yml.
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

errors=0

# Load .env if present
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

echo "Running production environment checks..."
echo ""

# --- DB_PASSWORD ---
if [ -z "${DB_PASSWORD:-}" ]; then
  echo -e "${RED}FAIL${NC}: DB_PASSWORD is not set"
  errors=$((errors + 1))
elif [ "$DB_PASSWORD" = "devpassword" ]; then
  echo -e "${RED}FAIL${NC}: DB_PASSWORD is still the default 'devpassword' — change it for production"
  errors=$((errors + 1))
else
  echo -e "${GREEN}OK${NC}:   DB_PASSWORD is set"
fi

# --- JWT_SECRET ---
if [ -z "${JWT_SECRET:-}" ]; then
  echo -e "${RED}FAIL${NC}: JWT_SECRET is not set"
  errors=$((errors + 1))
elif [ "$JWT_SECRET" = "dev-secret-change-me-at-least-32b" ] || [ "$JWT_SECRET" = "change-me-in-production-min-32bytes" ]; then
  echo -e "${RED}FAIL${NC}: JWT_SECRET is still a default value — generate a random secret for production"
  errors=$((errors + 1))
elif [ ${#JWT_SECRET} -lt 32 ]; then
  echo -e "${RED}FAIL${NC}: JWT_SECRET is too short (${#JWT_SECRET} chars) — must be at least 32 characters"
  errors=$((errors + 1))
else
  echo -e "${GREEN}OK${NC}:   JWT_SECRET is set (${#JWT_SECRET} chars)"
fi

# --- DEV_LOGIN_ENABLED ---
if [ "${DEV_LOGIN_ENABLED:-}" = "true" ]; then
  echo -e "${RED}FAIL${NC}: DEV_LOGIN_ENABLED is 'true' — must be 'false' in production"
  errors=$((errors + 1))
else
  echo -e "${GREEN}OK${NC}:   DEV_LOGIN_ENABLED is not 'true'"
fi

echo ""
if [ $errors -gt 0 ]; then
  echo -e "${RED}$errors check(s) failed. Fix the issues above before starting production.${NC}"
  exit 1
else
  echo -e "${GREEN}All checks passed.${NC}"
fi
