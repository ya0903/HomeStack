#!/usr/bin/env bash
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${BLUE}[HomeStack]${NC} $*"; }
ok()    { echo -e "${GREEN}[HomeStack]${NC} $*"; }
warn()  { echo -e "${YELLOW}[HomeStack]${NC} $*"; }
fail()  { echo -e "${RED}[HomeStack] ERROR:${NC} $*"; exit 1; }

echo -e "\n${BOLD}  HomeStack — Docker Compose Manager${NC}\n"

# ── Dependency checks ────────────────────────────────────────────────────────
command -v docker &>/dev/null       || fail "Docker is not installed. See: https://docs.docker.com/engine/install/"
docker compose version &>/dev/null  || fail "Docker Compose plugin not found. See: https://docs.docker.com/compose/install/"
command -v git &>/dev/null          || fail "Git is not installed. Run: sudo apt install git"

# ── Prompts ──────────────────────────────────────────────────────────────────
read -rp "$(echo -e "${BOLD}Install directory${NC} [/opt/homestack]: ")" INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-/opt/homestack}

read -rp "$(echo -e "${BOLD}Frontend port${NC} [7080]: ")" FRONTEND_PORT
FRONTEND_PORT=${FRONTEND_PORT:-7080}

read -rp "$(echo -e "${BOLD}Backend port${NC} [7079]: ")" BACKEND_PORT
BACKEND_PORT=${BACKEND_PORT:-7079}

# ── Clone or update ──────────────────────────────────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
  info "Updating existing installation in $INSTALL_DIR..."
  git -C "$INSTALL_DIR" pull
else
  info "Cloning HomeStack to $INSTALL_DIR..."
  mkdir -p "$(dirname "$INSTALL_DIR")"
  git clone https://github.com/ya0903/HomeStack.git "$INSTALL_DIR"
fi

# ── Write .env ───────────────────────────────────────────────────────────────
cat > "$INSTALL_DIR/.env" << EOF
FRONTEND_PORT=$FRONTEND_PORT
BACKEND_PORT=$BACKEND_PORT
AUTH_MODE=local
EOF
ok ".env written"

# ── Build and start ──────────────────────────────────────────────────────────
cd "$INSTALL_DIR"
info "Building and starting containers (first run may take a few minutes)..."
docker compose -f homestack.yml down 2>/dev/null || true
docker compose -f homestack.yml build
docker compose -f homestack.yml up -d

# ── Done ─────────────────────────────────────────────────────────────────────
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "your-server-ip")

echo ""
echo -e "${GREEN}${BOLD}  HomeStack is running!${NC}"
echo -e "  ${BOLD}URL:${NC}  http://${LOCAL_IP}:${FRONTEND_PORT}"
echo -e "  ${BOLD}Tip:${NC}  The first account you create becomes admin."
echo -e "  ${BOLD}Data:${NC} Stored in ${INSTALL_DIR}/data  (back this up)"
echo ""
