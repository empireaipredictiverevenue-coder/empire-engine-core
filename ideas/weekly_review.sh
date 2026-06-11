#!/bin/bash
# Empire AI · Predictive Revenue — Weekly Idea Review
#
# Runs every Sunday 18:00 server local. Reads parking_lot.md,
# applies the STARTING_POINT.md filter (see ideas/README.md), and
# writes a 1-pager review to ideas/review_YYYY-MM-DD.md.
#
# Wired into crontab by the user after the content is reviewed.
# Not auto-installed — you read the 1-pager, you decide.

set -euo pipefail

REPO="/root/empire-v49"
IDEAS_DIR="${REPO}/ideas"
PARKING="${IDEAS_DIR}/parking_lot.md"
TODAY=$(date +%Y-%m-%d)
REVIEW="${IDEAS_DIR}/review_${TODAY}.md"

if [ ! -f "${PARKING}" ]; then
    echo "no parking_lot.md at ${PARKING} — nothing to review"
    exit 0
fi

# Count active ideas
ACTIVE_COUNT=$(grep -c '^- \[' "${PARKING}" || true)

{
    echo "# Weekly Idea Review · ${TODAY}"
    echo
    echo "Active ideas in parking lot: ${ACTIVE_COUNT}"
    echo
    echo "## Filter (from STARTING_POINT.md)"
    echo
    echo "1. Does it serve the storm-damage lead-gen business directly?"
    echo "2. Does it produce a real, measurable outcome?"
    echo "3. Does it have at least 1 real data point to learn from?"
    echo
    echo "## Active lot"
    echo
    cat "${PARKING}"
    echo
    echo "## Decision"
    echo
    echo "(KEEP / DEFER / DROP per idea — fill in below)"
    echo
} > "${REVIEW}"

echo "wrote ${REVIEW}"
