#!/usr/bin/env bash
# Pre-flight checks for production deployment.
# Run before starting services with docker-compose.prod.yml.
set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

errors=0
warnings=0

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

# === Warnings (non-blocking) ===
echo ""
echo "Optional production checks..."
echo ""

# --- CORS_ORIGINS ---
if [ -z "${CORS_ORIGINS:-}" ] || echo "${CORS_ORIGINS:-}" | grep -q "localhost"; then
  echo -e "${YELLOW}WARN${NC}: CORS_ORIGINS contains 'localhost' or is unset — set to your production domain(s)"
  warnings=$((warnings + 1))
else
  echo -e "${GREEN}OK${NC}:   CORS_ORIGINS is set"
fi

# --- FRONTEND_URL ---
if [ -z "${FRONTEND_URL:-}" ] || echo "${FRONTEND_URL:-}" | grep -q "localhost"; then
  echo -e "${YELLOW}WARN${NC}: FRONTEND_URL contains 'localhost' or is unset — Slack links will point to localhost"
  warnings=$((warnings + 1))
else
  echo -e "${GREEN}OK${NC}:   FRONTEND_URL is set"
fi

# --- Google OAuth ---
if [ -z "${GOOGLE_CLIENT_ID:-}" ] || [ -z "${GOOGLE_CLIENT_SECRET:-}" ]; then
  echo -e "${YELLOW}WARN${NC}: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET is empty — Google OAuth will not work"
  warnings=$((warnings + 1))
else
  echo -e "${GREEN}OK${NC}:   Google OAuth credentials are set"
fi

# === Summary ===
echo ""
if [ $errors -gt 0 ]; then
  echo -e "${RED}$errors check(s) failed. Fix the issues above before starting production.${NC}"
  [ $warnings -gt 0 ] && echo -e "${YELLOW}$warnings warning(s) — review recommended but not required.${NC}"
  exit 1
else
  echo -e "${GREEN}All required checks passed.${NC}"
  [ $warnings -gt 0 ] && echo -e "${YELLOW}$warnings warning(s) — review recommended but not required.${NC}"
fi
