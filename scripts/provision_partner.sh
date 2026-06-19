#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# EMPIRE AI · WHITE-LABEL PARTNER PROVISIONER
# ═══════════════════════════════════════════════════════════════════════════
# One-command partner setup: registers the partner, provisions their Docker
# container, and outputs the deployed config.
#
# Usage:
#   ./scripts/provision_partner.sh --name "Acme Restoration" \\
#     --email "ceo@acme.com" --tier growth \\
#     --logo "https://acme.com/logo.png" --color "#00AAFF"
#
#   ./scripts/provision_partner.sh --list              # list active partners
#   ./scripts/provision_partner.sh --tiers              # show available tiers
#   ./scripts/provision_partner.sh --help               # show this help
#
# Requires:
#   - Docker (for container provisioning)
#   - Empire hub running on localhost:8001
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

HUB_URL="${HUB_URL:-http://localhost:8001}"
AUTH_TOKEN="${AUTH_TOKEN:-}"

# ── Colors for output ──────────────────────────────────────────────────
GREEN='\033[0;32m'
TEAL='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# ── Help ───────────────────────────────────────────────────────────────
print_help() {
    sed -n '2,18p' "$0" | sed 's/^# \?//'
}

# ── API call helper ────────────────────────────────────────────────────
# All white-label endpoints use FastAPI Query(...) params, so query params
# go in the URL, not the request body.
api() {
    local method="$1"
    local path="$2"
    local query="${3:-}"

    local url="$HUB_URL$path"
    [ -n "$query" ] && url="${url}?${query}"

    local curl_args=(
        -s
        -X "$method"
    )

    if [ -n "$AUTH_TOKEN" ]; then
        curl_args+=(-H "Authorization: Bearer $AUTH_TOKEN")
    fi

    curl "${curl_args[@]}" "$url"
}

# ── Provision a partner ────────────────────────────────────────────────
provision() {
    local name="" email="" tier="starter" company="" phone="" logo="" color="" domain=""

    while [ $# -gt 0 ]; do
        case "$1" in
            --name)    name="$2"; shift 2 ;;
            --email)   email="$2"; shift 2 ;;
            --tier)    tier="$2"; shift 2 ;;
            --company) company="$2"; shift 2 ;;
            --phone)   phone="$2"; shift 2 ;;
            --logo)    logo="$2"; shift 2 ;;
            --color)   color="$2"; shift 2 ;;
            --domain)  domain="$2"; shift 2 ;;
            *) echo -e "${RED}Unknown argument: $1${NC}"; exit 1 ;;
        esac
    done

    if [ -z "$name" ] || [ -z "$email" ]; then
        echo -e "${RED}Error: --name and --email are required${NC}"
        exit 1
    fi

    echo -e "${TEAL}═══ Provisioning Partner ═══${NC}"
    echo -e "  Name:    ${name}"
    echo -e "  Email:   ${email}"
    echo -e "  Tier:    ${tier}"
    echo -e "  Company: ${company:-$name}"
    echo ""

    # Step 1: Register partner
    echo -e "${YELLOW}→ Registering partner...${NC}"
    REG_QUERY="name=$(echo "$name" | sed 's/ /%20/g;s/&/%26/g')&email=$(echo "$email" | sed 's/ /%20/g;s/&/%26/g')&tier=$tier&company=$(echo "$company" | sed 's/ /%20/g;s/&/%26/g')&phone=$(echo "$phone" | sed 's/ /%20/g;s/&/%26/g')"
    REG_RESPONSE=$(api POST "/api/white-label/partner" "$REG_QUERY")
    PARTNER_ID=$(echo "$REG_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('partner',{}).get('partner_id',''))" 2>/dev/null || echo "")

    if [ -z "$PARTNER_ID" ]; then
        echo -e "${RED}✗ Registration failed:${NC}"
        echo "$REG_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$REG_RESPONSE"
        exit 1
    fi
    echo -e "${GREEN}✓ Partner registered: ${PARTNER_ID}${NC}"

    # Step 2: Apply branding if provided
    if [ -n "$logo" ] || [ -n "$color" ] || [ -n "$domain" ]; then
        echo -e "${YELLOW}→ Applying branding...${NC}"
        UPDATE_PATH="/api/white-label/partner/${PARTNER_ID}"
        UPDATE_PARAMS=""
        [ -n "$logo" ]   && UPDATE_PARAMS="${UPDATE_PARAMS}logo_url=$(echo "$logo" | sed 's/ /%20/g;s/&/%26/g')&"
        [ -n "$color" ]  && UPDATE_PARAMS="${UPDATE_PARAMS}primary_color=$(echo "$color" | sed 's/ /%20/g;s/&/%26/g')&"
        [ -n "$domain" ] && UPDATE_PARAMS="${UPDATE_PARAMS}custom_domain=$(echo "$domain" | sed 's/ /%20/g;s/&/%26/g')&"
        UPDATE_PARAMS="${UPDATE_PARAMS%&}"  # trim trailing &
        UPDATE_RESPONSE=$(api PATCH "$UPDATE_PATH" "$UPDATE_PARAMS")
        echo -e "${GREEN}✓ Branding applied${NC}"
    fi

    # Step 3: Provision container
    echo -e "${YELLOW}→ Provisioning container...${NC}"
    PROV_RESPONSE=$(api POST "/api/white-label/partner/${PARTNER_ID}/provision")
    PROV_STATUS=$(echo "$PROV_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('container',{}).get('status','failed'))" 2>/dev/null || echo "failed")

    if [ "$PROV_STATUS" = "running" ]; then
        PORT=$(echo "$PROV_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('container',{}).get('port',''))" 2>/dev/null || echo "")
        echo -e "${GREEN}✓ Container running on port ${PORT}${NC}"
    elif [ "$PROV_STATUS" = "config_generated" ]; then
        PORT=$(echo "$PROV_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('container',{}).get('port',''))" 2>/dev/null || echo "")
        echo -e "${YELLOW}⚠ Config generated (port ${PORT}). Deploy manually:${NC}"
        echo "  docker compose -f /root/empire-v49/docker-compose.yml up -d partner_${PARTNER_ID,,}"
    else
        echo -e "${RED}✗ Provisioning failed:${NC}"
        echo "$PROV_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$PROV_RESPONSE"
        exit 1
    fi

    echo ""
    echo -e "${TEAL}═══ Partner Summary ═══${NC}"
    echo -e "  Partner ID:  ${PARTNER_ID}"
    echo -e "  Name:        ${name}"
    echo -e "  Tier:        ${tier}"
    echo -e "  Status:      ${GREEN}active${NC}"
    echo -e "  Container:   ${PROV_STATUS}"
    [ -n "${PORT:-}" ] && echo -e "  Port:        ${PORT}"
    [ -n "${domain:-}" ] && echo -e "  Domain:      ${domain}"
    echo ""
    echo -e "  ${GREEN}✓ Partner ${name} is live!${NC}"
    echo ""
}

# ── List partners ──────────────────────────────────────────────────────
list_partners() {
    echo -e "${TEAL}═══ White-Label Partners ═══${NC}"
    RESPONSE=$(api GET "/api/white-label/partners")
    echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
partners = data.get('partners', [])
print(f\"  Total: {data.get('total', 0)}  |  Active: {data.get('active_count', 0)}  |  MRR: \${data.get('total_mrr', 0):.0f}/mo\")
print()
for p in partners:
    print(f\"  {p.get('partner_id','?'):20s}  {p.get('company','?'):25s}  {p.get('tier','?'):12s}  {p.get('status','?'):10s}  \${p.get('monthly_fee',0):.0f}/mo\")
" 2>/dev/null || echo "$RESPONSE" | python3 -m json.tool
}

# ── Show tiers ─────────────────────────────────────────────────────────
show_tiers() {
    echo -e "${TEAL}═══ Available Reseller Tiers ═══${NC}"
    RESPONSE=$(api GET "/api/white-label/tiers")
    echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
tiers = data.get('tiers', {})
for t, cfg in sorted(tiers.items()):
    print(f\"  {t.upper():12s}  \${cfg.get('monthly_price_usd',0):>5.0f}/mo  {cfg.get('max_containers',0):>3d} cntrs  {cfg.get('max_sub_accounts',0):>5d} subs  {cfg.get('revenue_split_pct',0):>3d}% split\")
    print(f\"  {'':12s}  {cfg.get('description','')}\")
    print()
" 2>/dev/null || echo "$RESPONSE" | python3 -m json.tool
}

# ════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════

case "${1:-}" in
    --help|-h)
        print_help
        ;;
    --list|-l)
        list_partners
        ;;
    --tiers|-t)
        show_tiers
        ;;
    --name|-n)
        shift
        provision "$@"
        ;;
    *)
        if [ $# -eq 0 ]; then
            print_help
        else
            provision "$@"
        fi
        ;;
esac
