#!/usr/bin/env bash
#
# Set up a reverse proxy (Caddy or nginx) for the Knowledge Elicitation Platform.
#
# Handles: package installation, frontend build, config generation,
# TLS certificate, service activation, and .env update.
#
# Usage:
#   bash scripts/setup-reverse-proxy.sh
#   bash scripts/setup-reverse-proxy.sh --domain knowledge.example.com
#   make setup-reverse-proxy
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- Colors and helpers ---

BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

info()  { printf "${CYAN}==> %s${NC}\n" "$*"; }
ok()    { printf "${GREEN} ok ${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}warn${NC} %s\n" "$*"; }
fail()  { printf "${RED}fail${NC} %s\n" "$*"; exit 1; }
ask()   { printf "${BOLD}%s${NC} " "$1"; }

prompt() {
    local var_name="$1" prompt_text="$2" default="${3:-}"
    if [ -n "$default" ]; then
        ask "$prompt_text [$default]:"
        read -r value
        eval "$var_name=\"${value:-$default}\""
    else
        ask "$prompt_text:"
        read -r value
        eval "$var_name=\"$value\""
    fi
}

confirm() {
    ask "$1 [y/N]:"
    read -r yn
    [[ "$yn" =~ ^[Yy] ]]
}

# --- Parse arguments ---

DOMAIN=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --domain) DOMAIN="$2"; shift 2 ;;
        --domain=*) DOMAIN="${1#*=}"; shift ;;
        -h|--help)
            echo "Usage: $0 [--domain DOMAIN]"
            echo ""
            echo "Options:"
            echo "  --domain DOMAIN   Domain name (prompted if not provided)"
            exit 0
            ;;
        *) fail "Unknown argument: $1 (use --help for usage)" ;;
    esac
done

# --- Preflight checks ---

echo
printf "${BOLD}%s${NC}\n" "Reverse Proxy Setup"
printf "${DIM}%s${NC}\n" "Installs and configures Caddy or nginx with TLS."
echo

# macOS warning
if [[ "$(uname -s)" == "Darwin" ]]; then
    warn "This script is intended for Linux production servers"
    warn "On macOS, access the app directly via http://localhost:5173"
    if ! confirm "Continue anyway?"; then
        exit 0
    fi
fi

# Sudo access
if [ "$(id -u)" -ne 0 ]; then
    if ! command -v sudo >/dev/null 2>&1; then
        fail "This script requires root access. Run with sudo or as root."
    fi
    SUDO="sudo"
    # Verify sudo works (prompts for password early)
    $SUDO true || fail "sudo authentication failed"
else
    SUDO=""
fi

# Detect package manager
detect_pkg_manager() {
    if command -v apt-get >/dev/null 2>&1; then
        echo "apt"
    elif command -v dnf >/dev/null 2>&1; then
        echo "dnf"
    elif command -v yum >/dev/null 2>&1; then
        echo "yum"
    elif command -v pacman >/dev/null 2>&1; then
        echo "pacman"
    else
        echo "unknown"
    fi
}

PKG_MANAGER=$(detect_pkg_manager)
if [ "$PKG_MANAGER" = "unknown" ]; then
    fail "Could not detect package manager (apt, dnf, yum, or pacman required)"
fi
ok "Package manager: $PKG_MANAGER"

# --- Domain ---

if [ -z "$DOMAIN" ]; then
    prompt DOMAIN "Domain name (e.g., knowledge.yourcompany.com)"
fi

if [ -z "$DOMAIN" ]; then
    fail "Domain name is required"
fi

# DNS verification
echo
info "Checking DNS for $DOMAIN..."

resolve_domain() {
    if command -v dig >/dev/null 2>&1; then
        dig +short "$1" 2>/dev/null | head -1
    elif command -v host >/dev/null 2>&1; then
        host "$1" 2>/dev/null | awk '/has address/ { print $4; exit }'
    elif command -v nslookup >/dev/null 2>&1; then
        nslookup "$1" 2>/dev/null | awk '/^Address: / { print $2; exit }'
    fi
}

RESOLVED_IP=$(resolve_domain "$DOMAIN") || true
SERVER_IP=$(curl -sf --max-time 5 https://api.ipify.org 2>/dev/null \
    || curl -sf --max-time 5 https://ifconfig.me 2>/dev/null) || true

if [ -z "$RESOLVED_IP" ]; then
    warn "DNS lookup failed for $DOMAIN"
    warn "TLS certificate acquisition requires DNS to be configured first"
    if ! confirm "Continue anyway? (you can re-run this script later)"; then
        exit 0
    fi
elif [ -n "$SERVER_IP" ] && [ "$RESOLVED_IP" != "$SERVER_IP" ]; then
    warn "$DOMAIN resolves to $RESOLVED_IP but this server's public IP is $SERVER_IP"
    if ! confirm "Continue anyway?"; then
        exit 0
    fi
else
    ok "$DOMAIN resolves to $RESOLVED_IP"
fi

# --- Choose proxy ---

echo
printf "${BOLD}Choose a reverse proxy:${NC}\n"
echo "  1) Caddy  — automatic TLS, zero config (recommended)"
echo "  2) nginx  — manual TLS via Certbot"
echo
ask "Choice [1]:"
read -r PROXY_CHOICE
PROXY_CHOICE="${PROXY_CHOICE:-1}"

case "$PROXY_CHOICE" in
    1) PROXY="caddy" ;;
    2) PROXY="nginx" ;;
    *) fail "Invalid choice: $PROXY_CHOICE" ;;
esac

ok "Selected: $PROXY"

# --- Build frontend ---

echo
info "Building frontend static files..."
FRONTEND_DIR="$PROJECT_ROOT/frontend"

if [ ! -d "$FRONTEND_DIR" ]; then
    fail "Frontend directory not found at $FRONTEND_DIR"
fi

if command -v npm >/dev/null 2>&1; then
    (cd "$FRONTEND_DIR" && npm install --silent && npm run build)
elif command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    info "npm not found locally — building via Docker..."
    docker compose -f "$PROJECT_ROOT/docker-compose.yml" run --rm \
        -w /app web sh -c "npm run build"
else
    fail "npm or Docker is required to build the frontend. Install Node.js 18+ or Docker."
fi

DIST_DIR="$FRONTEND_DIR/dist"
if [ ! -f "$DIST_DIR/index.html" ]; then
    fail "Frontend build failed — $DIST_DIR/index.html not found"
fi
ok "Frontend built: $DIST_DIR"

# Deploy to web root
WEB_ROOT="/var/www/knowledge-elicitation"
info "Deploying frontend to $WEB_ROOT..."
$SUDO mkdir -p "$WEB_ROOT"
$SUDO rm -rf "${WEB_ROOT:?}/"*
$SUDO cp -r "$DIST_DIR/." "$WEB_ROOT/"
ok "Frontend deployed to $WEB_ROOT"

# --- Install and configure: Caddy ---

install_caddy() {
    if command -v caddy >/dev/null 2>&1; then
        ok "Caddy already installed ($(caddy version 2>&1 | head -1))"
    else
        info "Installing Caddy..."
        case "$PKG_MANAGER" in
            apt)
                $SUDO apt-get install -y debian-keyring debian-archive-keyring apt-transport-https >/dev/null
                curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
                    | $SUDO gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg 2>/dev/null
                curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
                    | $SUDO tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
                $SUDO apt-get update >/dev/null
                $SUDO apt-get install -y caddy >/dev/null
                ;;
            dnf)
                $SUDO dnf install -y 'dnf-command(copr)' >/dev/null 2>&1 || true
                $SUDO dnf copr enable -y @caddy/caddy >/dev/null 2>&1
                $SUDO dnf install -y caddy >/dev/null
                ;;
            yum)
                $SUDO yum install -y yum-plugin-copr >/dev/null 2>&1 || true
                $SUDO yum copr enable -y @caddy/caddy >/dev/null 2>&1
                $SUDO yum install -y caddy >/dev/null
                ;;
            pacman)
                $SUDO pacman -S --noconfirm caddy >/dev/null
                ;;
        esac
        ok "Caddy installed"
    fi

    # Check for existing config
    CADDY_CONFIG="/etc/caddy/Caddyfile"
    if [ -f "$CADDY_CONFIG" ]; then
        if grep -q "$DOMAIN" "$CADDY_CONFIG" 2>/dev/null; then
            warn "Caddyfile already has a block for $DOMAIN"
            if ! confirm "Overwrite the Caddyfile?"; then
                info "Skipping config write — edit $CADDY_CONFIG manually"
                return
            fi
        elif [ -s "$CADDY_CONFIG" ]; then
            warn "Caddyfile has existing configuration"
            if ! confirm "Overwrite? (backup saved to ${CADDY_CONFIG}.bak)"; then
                info "Skipping config write — add the block to $CADDY_CONFIG manually"
                return
            fi
            $SUDO cp "$CADDY_CONFIG" "${CADDY_CONFIG}.bak"
            ok "Backup: ${CADDY_CONFIG}.bak"
        fi
    fi

    $SUDO tee "$CADDY_CONFIG" > /dev/null << EOF
$DOMAIN {
    handle /api/* {
        reverse_proxy localhost:8000
    }

    handle /health {
        reverse_proxy localhost:8000
    }

    handle {
        root * $WEB_ROOT
        try_files {path} /index.html
        file_server
    }
}
EOF
    ok "Written $CADDY_CONFIG"

    $SUDO systemctl enable caddy >/dev/null 2>&1
    $SUDO systemctl restart caddy
    ok "Caddy started — TLS certificate will be obtained automatically"
}

# --- Install and configure: nginx ---

install_nginx() {
    if command -v nginx >/dev/null 2>&1; then
        ok "nginx already installed ($(nginx -v 2>&1))"
    else
        info "Installing nginx..."
        case "$PKG_MANAGER" in
            apt) $SUDO apt-get install -y nginx >/dev/null ;;
            dnf|yum) $SUDO $PKG_MANAGER install -y nginx >/dev/null ;;
            pacman) $SUDO pacman -S --noconfirm nginx >/dev/null ;;
        esac
        ok "nginx installed"
    fi

    # Check for existing config
    NGINX_SITE="/etc/nginx/sites-available/knowledge-elicitation"
    if [ -f "$NGINX_SITE" ]; then
        warn "nginx site config already exists at $NGINX_SITE"
        if ! confirm "Overwrite?"; then
            info "Skipping config write — edit $NGINX_SITE manually"
            return
        fi
    fi

    # Write HTTP-only config first (Certbot will add TLS)
    $SUDO mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
    $SUDO tee "$NGINX_SITE" > /dev/null << 'NGINX_INNER'
server {
    listen 80;
    server_name DOMAIN_PLACEHOLDER;

    root WEB_ROOT_PLACEHOLDER;
    index index.html;

    # API and SSE proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support — disable buffering and set long timeouts
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # Health check proxy
    location = /health {
        proxy_pass http://127.0.0.1:8000;
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINX_INNER

    # Replace placeholders (avoids shell variable conflicts with nginx $vars)
    $SUDO sed -i "s|DOMAIN_PLACEHOLDER|$DOMAIN|g" "$NGINX_SITE"
    $SUDO sed -i "s|WEB_ROOT_PLACEHOLDER|$WEB_ROOT|g" "$NGINX_SITE"
    ok "Written $NGINX_SITE"

    # Enable site
    if [ -d /etc/nginx/sites-enabled ]; then
        $SUDO ln -sf "$NGINX_SITE" /etc/nginx/sites-enabled/
    fi

    $SUDO nginx -t || fail "nginx config test failed — check $NGINX_SITE"
    $SUDO systemctl enable nginx >/dev/null 2>&1
    $SUDO systemctl restart nginx
    ok "nginx started (HTTP only)"

    # Obtain TLS via Certbot
    if ! command -v certbot >/dev/null 2>&1; then
        info "Installing Certbot..."
        case "$PKG_MANAGER" in
            apt) $SUDO apt-get install -y certbot python3-certbot-nginx >/dev/null ;;
            dnf|yum) $SUDO $PKG_MANAGER install -y certbot python3-certbot-nginx >/dev/null ;;
            pacman) $SUDO pacman -S --noconfirm certbot certbot-nginx >/dev/null ;;
        esac
        ok "Certbot installed"
    fi

    echo
    info "Obtaining TLS certificate via Certbot..."
    info "(Certbot may ask for your email and Terms of Service agreement)"
    echo
    if $SUDO certbot --nginx -d "$DOMAIN" --redirect; then
        ok "TLS certificate obtained — nginx reconfigured for HTTPS"
    else
        warn "Certbot failed — site is running on HTTP only"
        warn "Fix DNS, then re-run: sudo certbot --nginx -d $DOMAIN --redirect"
    fi
}

# --- Run installation ---

echo
if [ "$PROXY" = "caddy" ]; then
    install_caddy
else
    install_nginx
fi

# --- Update .env ---

ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    echo
    if confirm "Update .env for production? (FRONTEND_URL, CORS_ORIGINS, DEV_LOGIN_ENABLED)"; then
        sed -i.bak "s|^FRONTEND_URL=.*|FRONTEND_URL=https://$DOMAIN|" "$ENV_FILE"
        sed -i.bak "s|^CORS_ORIGINS=.*|CORS_ORIGINS=[\"https://$DOMAIN\"]|" "$ENV_FILE"
        sed -i.bak "s|^DEV_LOGIN_ENABLED=.*|DEV_LOGIN_ENABLED=false|" "$ENV_FILE"
        rm -f "${ENV_FILE}.bak"
        ok "Updated .env — FRONTEND_URL=https://$DOMAIN, DEV_LOGIN_ENABLED=false"

        if command -v docker >/dev/null 2>&1; then
            info "Restarting services to pick up .env changes..."
            (cd "$PROJECT_ROOT" && docker compose restart api worker >/dev/null 2>&1) || true
            ok "Services restarted"
        fi
    fi
fi

# --- Verify ---

echo
info "Verifying deployment..."
sleep 2

HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "https://$DOMAIN" --max-time 10 2>/dev/null) || true
if [ "$HTTP_CODE" = "200" ]; then
    ok "https://$DOMAIN is live (HTTP $HTTP_CODE)"
else
    warn "https://$DOMAIN returned HTTP ${HTTP_CODE:-timeout}"
    if [ "$PROXY" = "caddy" ]; then
        warn "Caddy may still be provisioning the TLS certificate — try again in a moment"
    fi
fi

API_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "https://$DOMAIN/api/v1/auth/config" --max-time 10 2>/dev/null) || true
if [ "$API_CODE" = "200" ]; then
    ok "API reachable through the proxy"
else
    warn "API returned HTTP ${API_CODE:-timeout} — ensure Docker services are running"
fi

# --- Summary ---

echo
printf "${BOLD}%s${NC}\n" "Reverse proxy setup complete!"
echo
echo "  Proxy:    $PROXY"
echo "  Domain:   https://$DOMAIN"
echo "  Frontend: $WEB_ROOT"
echo
if [ ! -f "$ENV_FILE" ] || grep -q "DEV_LOGIN_ENABLED=true" "$ENV_FILE" 2>/dev/null; then
    echo "Remaining steps:"
    echo "  1. Update .env: FRONTEND_URL=https://$DOMAIN"
    echo "  2. Update .env: CORS_ORIGINS=[\"https://$DOMAIN\"]"
    echo "  3. Update .env: DEV_LOGIN_ENABLED=false"
    echo "  4. Restart: docker compose restart api worker"
else
    echo "Open https://$DOMAIN in a browser to verify."
fi
