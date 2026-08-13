#!/usr/bin/env bash
# Setup AWSOME (Avalanche Warning Service Operational Meteo Environment) toolchain.
#
# AWSOME is an open-source framework (AGPL v3) for automating and visualizing
# weather and snow cover simulations in support of avalanche forecasting.
# Source: https://gitlab.com/avalanche-warning
#
# Prerequisites:
#   - SNOWPACK built and installed (scripts/build_snowpack.sh)
#   - Python 3.10+
#   - pip install -r backend/requirements-snowpack.txt
#
# Usage:
#   bash scripts/setup_awsome.sh          # full setup
#   bash scripts/setup_awsome.sh --check  # verify installation
#   bash scripts/setup_awsome.sh --clean  # remove AWSOME
set -euo pipefail

AWSOME_DIR="${AWSOME_DIR:-${HOME}/awsome}"
AWSOME_REPO="https://gitlab.com/avalanche-warning/awsome.git"
AWSOME_COMMIT="${AWSOME_COMMIT:-}"
AWSOME_VENV="${AWSOME_DIR}/venv"

# --check mode
if [[ "${1:-}" == "--check" ]]; then
    if [[ -d "${AWSOME_DIR}" ]] && [[ -f "${AWSOME_DIR}/awsome-cli.py" ]]; then
        echo "AWSOME: INSTALLED at ${AWSOME_DIR}"
        if [[ -f "${AWSOME_DIR}/config/regions.yaml" ]]; then
            echo "  Region config: ${AWSOME_DIR}/config/regions.yaml"
        fi
        exit 0
    else
        echo "AWSOME: NOT INSTALLED (run without --check to install)"
        exit 1
    fi
fi

# --clean mode
if [[ "${1:-}" == "--clean" ]]; then
    echo "Removing AWSOME installation..."
    rm -rf "${AWSOME_DIR}"
    echo "Done."
    exit 0
fi

echo "=== AWSOME Toolchain Setup (AGPL v3, zero cost) ==="
echo "Install dir: ${AWSOME_DIR}"
echo ""

if [[ ! "${AWSOME_COMMIT}" =~ ^[0-9a-fA-F]{40}$ ]]; then
    echo "ERROR: AWSOME_COMMIT must be an exact 40-character commit hash."
    exit 1
fi

# Check prerequisites
command -v git >/dev/null 2>&1 || { echo "ERROR: git not found."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found."; exit 1; }

# Clone AWSOME at the required exact commit; never pull floating HEAD.
if [[ ! -d "${AWSOME_DIR}" ]]; then
    echo "Cloning AWSOME at ${AWSOME_COMMIT} from GitLab..."
    git clone "${AWSOME_REPO}" "${AWSOME_DIR}"
fi
git -C "${AWSOME_DIR}" checkout --detach "${AWSOME_COMMIT}"
[[ "$(git -C "${AWSOME_DIR}" rev-parse HEAD)" == "${AWSOME_COMMIT}" ]] || {
    echo "ERROR: AWSOME checkout does not match pinned commit"; exit 1;
}

# Create virtual environment
if [[ ! -d "${AWSOME_VENV}" ]]; then
    echo "Creating Python venv..."
    python3 -m venv "${AWSOME_VENV}"
fi

# Install AWSOME Python dependencies
# Phase 0.5: removed permissive 'snowpacktools 2>/dev/null || true' —
# snowpacktools is AGPLv3 with no tagged releases. If installation fails,
# it must be reported, not silently ignored. The operator must review
# the snowpacktools revision and AGPLv3 obligations before installation.
echo "Installing AWSOME Python dependencies..."
"${AWSOME_VENV}/bin/pip" install --quiet --upgrade pip
"${AWSOME_VENV}/bin/pip" install --quiet \
    numpy pandas xarray netCDF4 \
    matplotlib cartopy \
    pyyaml requests

# Phase 0.5: snowpacktools installation is now explicit, not permissive.
# The operator must pin a specific revision and review AGPLv3 obligations.
echo ""
echo "NOTE: snowpacktools is NOT installed automatically."
echo "  snowpacktools is AGPLv3 with no tagged releases in the current repository."
echo "  To install, the operator must:"
echo "    1. Review the snowpacktools revision at https://gitlab.com/avalanche-warning/snow-cover/postprocessing/snowpacktools"
echo "    2. Pin a specific commit hash"
echo "    3. Review AGPLv3 redistribution obligations"
echo "    4. Install explicitly: ${AWSOME_VENV}/bin/pip install git+https://gitlab.com/avalanche-warning/snow-cover/postprocessing/snowpacktools.git@<commit-hash>"
echo ""

# Link region config
echo "Linking region configuration..."
mkdir -p "${AWSOME_DIR}/config"
if [[ -f "$(pwd)/config/awsome_regions.yaml" ]]; then
    cp "$(pwd)/config/awsome_regions.yaml" "${AWSOME_DIR}/config/regions.yaml"
    echo "  Copied config/awsome_regions.yaml → ${AWSOME_DIR}/config/regions.yaml"
fi

# Verify
echo ""
echo "=== Setup Complete ==="
echo "AWSOME installed to: ${AWSOME_DIR}"
echo "Virtual env: ${AWSOME_VENV}"
echo ""
echo "Set these environment variables:"
echo "  export AWSOME_HOME=${AWSOME_DIR}"
echo "  export PATH=${AWSOME_VENV}/bin:\$PATH"
echo ""
echo "To run AWSOME for a region:"
echo "  python3 backend/common/awsome_runner.py --region himalayas_nepal"
