#!/usr/bin/env bash
# =============================================================================
# Cassette Update Script for CI
# =============================================================================
#
# Purpose: Commit and push cassette updates from CI environment
#
# Usage:
#   ./update-cassettes.sh [--version VERSION] [--branch BRANCH]
#
# Environment Variables:
#   CIVI_VERSION      - CiviCRM version for commit message
#   GITHUB_TOKEN      - GitHub token for authentication
#   GITHUB_REPOSITORY - Repository in owner/repo format
#   GITHUB_RUN_ID     - Current workflow run ID
#
# Exit Codes:
#   0 - Success (changes committed or no changes)
#   1 - Error during git operations
#   2 - Missing required environment variables
#
# Phase 8.5.12: Nightly CI workflow support
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Default values
CIVI_VERSION="${CIVI_VERSION:-unknown}"
BRANCH_NAME="chore/update-cassettes-$(date +%Y%m%d)"
CASSETTE_DIR="tests/cassettes"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# -----------------------------------------------------------------------------
# Functions
# -----------------------------------------------------------------------------

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Commit and push cassette updates from CI.

Options:
    -v, --version VERSION    CiviCRM version for commit message
    -b, --branch BRANCH      Branch name for updates (default: chore/update-cassettes-YYYYMMDD)
    -d, --dry-run            Show what would be done without making changes
    -h, --help               Show this help message

Environment Variables:
    CIVI_VERSION             CiviCRM version (alternative to --version)
    GITHUB_TOKEN             GitHub token for pushing changes
    GITHUB_REPOSITORY        Repository in owner/repo format
    GITHUB_RUN_ID            Current workflow run ID

Examples:
    # Basic usage
    ./update-cassettes.sh

    # With specific version
    ./update-cassettes.sh --version 5.74

    # Dry run to see changes
    ./update-cassettes.sh --dry-run
EOF
}

check_changes() {
    log_info "Checking for cassette changes..."

    cd "$REPO_ROOT"

    if git diff --quiet "$CASSETTE_DIR/"; then
        log_info "No cassette changes detected."
        return 1
    else
        log_info "Cassette changes detected:"
        git diff --stat "$CASSETTE_DIR/"
        return 0
    fi
}

configure_git() {
    log_info "Configuring git..."

    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"

    # Configure remote if using token
    if [[ -n "${GITHUB_TOKEN:-}" ]] && [[ -n "${GITHUB_REPOSITORY:-}" ]]; then
        git remote set-url origin "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
    fi
}

create_branch() {
    log_info "Creating branch: $BRANCH_NAME"

    # Check if branch already exists
    if git rev-parse --verify "origin/$BRANCH_NAME" >/dev/null 2>&1; then
        log_warn "Branch already exists, checking it out..."
        git checkout "$BRANCH_NAME"
        git pull origin "$BRANCH_NAME" || true
    else
        git checkout -b "$BRANCH_NAME"
    fi
}

commit_changes() {
    log_info "Committing cassette changes..."

    cd "$REPO_ROOT"

    # Stage cassette changes
    git add "$CASSETTE_DIR/"

    # Create commit message
    local run_info=""
    if [[ -n "${GITHUB_RUN_ID:-}" ]]; then
        run_info="Run ID: ${GITHUB_RUN_ID}"
    fi

    cat > /tmp/commit-msg.txt << EOF
chore(cassettes): update API cassettes for CiviCRM ${CIVI_VERSION}

Automated cassette update from nightly compatibility tests.

CiviCRM Version: ${CIVI_VERSION}
${run_info}
Workflow: Nightly Compatibility

Changes:
$(git diff --cached --stat "$CASSETTE_DIR/" | head -20)
EOF

    git commit -F /tmp/commit-msg.txt
}

push_changes() {
    log_info "Pushing changes to remote..."

    git push -u origin "$BRANCH_NAME"
}

# -----------------------------------------------------------------------------
# Parse Arguments
# -----------------------------------------------------------------------------

DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--version)
            CIVI_VERSION="$2"
            shift 2
            ;;
        -b|--branch)
            BRANCH_NAME="$2"
            shift 2
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    log_info "=== Cassette Update Script ==="
    log_info "CiviCRM Version: $CIVI_VERSION"
    log_info "Branch: $BRANCH_NAME"
    log_info "Repository Root: $REPO_ROOT"

    cd "$REPO_ROOT"

    # Check for changes
    if ! check_changes; then
        log_info "No changes to commit. Exiting."
        exit 0
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN: Would commit and push the following changes:"
        git diff --stat "$CASSETTE_DIR/"
        exit 0
    fi

    # Configure git
    configure_git

    # Create branch
    create_branch

    # Commit changes
    commit_changes

    # Push changes
    push_changes

    log_info "=== Cassette update complete ==="
    log_info "Branch '$BRANCH_NAME' has been pushed to remote."
    log_info "Create a pull request to merge these changes."
}

main "$@"
