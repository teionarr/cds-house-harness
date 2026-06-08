#!/usr/bin/env bash
# House Harness Engine — installer
#   ./install.sh             build & start the full stack locally
#   APP_PORT=9000 ./install.sh   override the port
# Runs from the extracted submission directory. Docker does the heavy lifting,
# so the reviewer's first command is one command — and it's idempotent.
set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────────────
PROJECT="${PROJECT:-house-harness}"
APP_PORT="${APP_PORT:-8080}"
COMPOSE="docker compose"

# ── Helpers ─────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'
info()  { printf "${GREEN}==> %s${NC}\n" "$1"; }
warn()  { printf "${YELLOW}WARNING: %s${NC}\n" "$1"; }
die()   { printf "${RED}ERROR: %s${NC}\n" "$1" >&2; exit 1; }

# ── Banner ──────────────────────────────────────────────────────────────────
printf "\n${BOLD}  House Harness Engine — agent-facing ontology over the company${NC}\n\n"

# ── Preflight ───────────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || die "Docker is required. Install it and retry."
$COMPOSE version >/dev/null 2>&1 || die "Docker Compose v2 is required (got none)."

# ── Env: Doppler if configured, else .env (idempotent) ─────────────────────
RUNNER=()
if command -v doppler >/dev/null 2>&1 && doppler configure get config >/dev/null 2>&1; then
  info "Doppler configured — injecting secrets at runtime (none written to disk)."
  RUNNER=(doppler run --)
else
  if [ ! -f .env ]; then
    cp .env.example .env
    warn ".env created from .env.example — add ANTHROPIC_API_KEY (required). LANGSMITH_API_KEY is optional (tracing auto-off without it); Doppler is optional too."
  fi
  info "Using .env for configuration (no Doppler project linked)."
fi

# ── Build & start ───────────────────────────────────────────────────────────
info "Building and starting $PROJECT ..."
"${RUNNER[@]}" $COMPOSE up -d --build

# ── Health check ────────────────────────────────────────────────────────────
info "Waiting for the service on :$APP_PORT ..."
for _ in $(seq 1 30); do
  if curl -fsS "http://localhost:$APP_PORT/health" >/dev/null 2>&1; then
    info "Up. The agent interface is ready:"
    printf "    HTTP/MCP:  http://localhost:%s\n" "$APP_PORT"
    printf "    MCP:       claude mcp add --transport http house-harness http://localhost:%s/mcp\n" "$APP_PORT"
    printf "    Ask:       curl -s localhost:%s/ask -H \"Authorization: Bearer \$HOUSE_HARNESS_API_TOKEN\" -d '{\"q\":\"Who reports to the CEO?\"}'\n\n" "$APP_PORT"
    exit 0
  fi
  sleep 2
done
die "Service did not become healthy in time. Inspect with: $COMPOSE logs"
