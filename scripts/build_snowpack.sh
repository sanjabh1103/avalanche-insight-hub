#!/usr/bin/env bash
# Build SNOWPACK C++ library + MeteoIO from source (LGPL v3, zero cost).
#
# Prerequisites:
#   - CMake >= 3.16
#   - GCC >= 9 or Clang >= 10
#   - libproj, libstdc++ (typically pre-installed on Ubuntu)
#   OR Docker (for --docker mode, recommended on macOS)
#
# Usage:
#   bash scripts/build_snowpack.sh              # full native build (Linux)
#   bash scripts/build_snowpack.sh --docker     # Docker build (macOS/CI, recommended)
#   bash scripts/build_snowpack.sh --check      # check if already built
#   bash scripts/build_snowpack.sh --clean      # remove build artifacts
set -euo pipefail

SNOWPACK_DIR="${SNOWPACK_DIR:-${HOME}/snowpack-build}"
SNOWPACK_REPO="https://code.wsl.ch/snow-models/snowpack.git"
MeteoIO_REPO="https://code.wsl.ch/snow-models/meteoio.git"
METEOIO_COMMIT="${METEOIO_COMMIT:-}"
SNOWPACK_COMMIT="${SNOWPACK_COMMIT:-}"
TOOLCHAIN_MANIFEST_ID="${TOOLCHAIN_MANIFEST_ID:-}"
UBUNTU_BASE_DIGEST="${UBUNTU_BASE_DIGEST:-}"
PYTHON_BASE_DIGEST="${PYTHON_BASE_DIGEST:-}"
INSTALL_PREFIX="${SNOWPACK_DIR}/install"
BUILD_DIR="${SNOWPACK_DIR}/build"

# --docker mode: build inside Docker container (works on macOS)
if [[ "${1:-}" == "--docker" ]]; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "ERROR: docker not found. Install Docker Desktop first."
        exit 1
    fi
    if [[ ! "${METEOIO_COMMIT}" =~ ^[0-9a-fA-F]{40}$ || ! "${SNOWPACK_COMMIT}" =~ ^[0-9a-fA-F]{40}$ ]]; then
        echo "ERROR: METEOIO_COMMIT and SNOWPACK_COMMIT must be exact 40-character hashes."
        exit 1
    fi
    if [[ -z "${TOOLCHAIN_MANIFEST_ID}" || ! "${UBUNTU_BASE_DIGEST}" =~ ^sha256:[0-9a-fA-F]{64}$ || ! "${PYTHON_BASE_DIGEST}" =~ ^sha256:[0-9a-fA-F]{64}$ ]]; then
        echo "ERROR: TOOLCHAIN_MANIFEST_ID and immutable Ubuntu/Python base digests are required."
        exit 1
    fi
    echo "=== Building SNOWPACK in Docker (multi-stage) ==="
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
    docker build -f "${PROJECT_ROOT}/Dockerfile.snowpack" \
        --build-arg METEOIO_COMMIT="${METEOIO_COMMIT}" \
        --build-arg SNOWPACK_COMMIT="${SNOWPACK_COMMIT}" \
        --build-arg TOOLCHAIN_MANIFEST_ID="${TOOLCHAIN_MANIFEST_ID}" \
        --build-arg UBUNTU_BASE_DIGEST="${UBUNTU_BASE_DIGEST}" \
        --build-arg PYTHON_BASE_DIGEST="${PYTHON_BASE_DIGEST}" \
        -t avalanche-snowpack "${PROJECT_ROOT}"
    echo ""
    echo "=== Docker Build Complete ==="
    echo "Image: avalanche-snowpack"
    echo ""
    echo "Test COSIPY:"
    echo "  docker run --rm avalanche-snowpack python3 -c \"from cosipy.cpkernel import cosipy_core; print('COSIPY OK')\""
    echo ""
    echo "Test SNOWPACK binary:"
    echo "  docker run --rm avalanche-snowpack which snowpack"
    echo ""
    echo "Run pipeline inside container:"
    echo "  docker run --rm -v \"\${PWD}:/app/workspace\" -w /app/workspace avalanche-snowpack python3 -m backend.common.awsome_runner --validate"
    exit 0
fi

# --check mode: verify installation exists
# Phase 0.5: verify the executable, not just static libraries.
# Static libraries alone do not prove a working SNOWPACK installation.
if [[ "${1:-}" == "--check" ]]; then
    local_ok=true
    if [[ -f "${INSTALL_PREFIX}/lib/libsnowpack.a" ]] && [[ -f "${INSTALL_PREFIX}/lib/libmeteoio.a" ]]; then
        echo "SNOWPACK: LIBRARIES INSTALLED at ${INSTALL_PREFIX}"
        echo "  libsnowpack: $(ls -la ${INSTALL_PREFIX}/lib/libsnowpack.a 2>/dev/null | awk '{print $5}') bytes"
        echo "  libmeteoio:  $(ls -la ${INSTALL_PREFIX}/lib/libmeteoio.a 2>/dev/null | awk '{print $5}') bytes"
    else
        echo "SNOWPACK: LIBRARIES NOT INSTALLED (run without --check to build)"
        local_ok=false
    fi
    # Phase 0.5: verify the executable exists and runs
    if [[ -x "${INSTALL_PREFIX}/bin/snowpack" ]]; then
        echo "  snowpack binary: ${INSTALL_PREFIX}/bin/snowpack"
        version_cwd="$(mktemp -d)"
        if (cd "${version_cwd}" && "${INSTALL_PREFIX}/bin/snowpack" --version 2>/dev/null); then
            echo "  snowpack --version: OK"
        else
            echo "  ERROR: snowpack --version failed"
            local_ok=false
        fi
        rmdir "${version_cwd}" 2>/dev/null || true
    else
        echo "  ERROR: snowpack executable not found at ${INSTALL_PREFIX}/bin/snowpack"
        echo "  Static libraries alone do not prove a working installation."
        local_ok=false
    fi
    if [[ "$local_ok" == "true" ]]; then
        exit 0
    else
        exit 1
    fi
fi

# --clean mode: remove build artifacts
if [[ "${1:-}" == "--clean" ]]; then
    echo "Cleaning SNOWPACK build artifacts..."
    rm -rf "${BUILD_DIR}" "${INSTALL_PREFIX}"
    echo "Done."
    exit 0
fi

echo "=== SNOWPACK C++ Build (LGPL v3, zero cost) ==="
echo "Build dir: ${SNOWPACK_DIR}"
echo "Install prefix: ${INSTALL_PREFIX}"
echo ""

if [[ ! "${METEOIO_COMMIT}" =~ ^[0-9a-fA-F]{40}$ || ! "${SNOWPACK_COMMIT}" =~ ^[0-9a-fA-F]{40}$ ]]; then
    echo "ERROR: METEOIO_COMMIT and SNOWPACK_COMMIT must be exact 40-character hashes."
    exit 1
fi

# Check prerequisites
command -v cmake >/dev/null 2>&1 || { echo "ERROR: cmake not found. Install: sudo apt-get install cmake"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "ERROR: git not found."; exit 1; }

# Clone MeteoIO (SNOWPACK dependency) at the required exact commit.
if [[ ! -d "${SNOWPACK_DIR}/meteoio" ]]; then
    echo "Cloning MeteoIO at ${METEOIO_COMMIT}..."
    git clone "${MeteoIO_REPO}" "${SNOWPACK_DIR}/meteoio"
fi
git -C "${SNOWPACK_DIR}/meteoio" checkout --detach "${METEOIO_COMMIT}"
[[ "$(git -C "${SNOWPACK_DIR}/meteoio" rev-parse HEAD)" == "${METEOIO_COMMIT}" ]] || {
    echo "ERROR: MeteoIO checkout does not match pinned commit"; exit 1;
}

# Clone SNOWPACK at the required exact commit.
if [[ ! -d "${SNOWPACK_DIR}/snowpack" ]]; then
    echo "Cloning SNOWPACK at ${SNOWPACK_COMMIT}..."
    git clone "${SNOWPACK_REPO}" "${SNOWPACK_DIR}/snowpack"
fi
git -C "${SNOWPACK_DIR}/snowpack" checkout --detach "${SNOWPACK_COMMIT}"
[[ "$(git -C "${SNOWPACK_DIR}/snowpack" rev-parse HEAD)" == "${SNOWPACK_COMMIT}" ]] || {
    echo "ERROR: SNOWPACK checkout does not match pinned commit"; exit 1;
}

# Build MeteoIO
echo ""
echo "=== Building MeteoIO ==="
MeteoIO_BUILD="${BUILD_DIR}/meteoio"
mkdir -p "${MeteoIO_BUILD}"
cmake -S "${SNOWPACK_DIR}/meteoio" -B "${MeteoIO_BUILD}" \
    -DCMAKE_INSTALL_PREFIX="${INSTALL_PREFIX}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=OFF \
    -DBUILD_STATIC_LIBS=ON \
    -DPLUGIN_PNG=OFF \
    -DPLUGIN_ARCGIS=OFF \
    -DPLUGIN_GDAL=OFF \
    2>&1 | tail -5

cmake --build "${MeteoIO_BUILD}" --parallel "$(nproc 2>/dev/null || echo 4)" 2>&1 | tail -5
cmake --install "${MeteoIO_BUILD}" 2>&1 | tail -3

# Build SNOWPACK
echo ""
echo "=== Building SNOWPACK ==="
SNOWPACK_BUILD="${BUILD_DIR}/snowpack"
mkdir -p "${SNOWPACK_BUILD}"
cmake -S "${SNOWPACK_DIR}/snowpack" -B "${SNOWPACK_BUILD}" \
    -DCMAKE_INSTALL_PREFIX="${INSTALL_PREFIX}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=OFF \
    -DBUILD_STATIC_LIBS=ON \
    -DMETEOIO_ROOT="${INSTALL_PREFIX}" \
    -DENABLE_PYTHON=ON \
    2>&1 | tail -5

cmake --build "${SNOWPACK_BUILD}" --parallel "$(nproc 2>/dev/null || echo 4)" 2>&1 | tail -5
cmake --install "${SNOWPACK_BUILD}" 2>&1 | tail -3

echo ""
echo "=== Build Complete ==="
echo "Libraries installed to: ${INSTALL_PREFIX}/lib/"
echo "Headers installed to: ${INSTALL_PREFIX}/include/"
echo ""
echo "Set these environment variables for Python bindings:"
echo "  export SNOWPACK_HOME=${INSTALL_PREFIX}"
echo "  export LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:\$LD_LIBRARY_PATH"

# Verify
if [[ -f "${INSTALL_PREFIX}/lib/libsnowpack.a" ]]; then
    echo ""
    echo "VERIFICATION: libsnowpack.a found — build successful"
else
    echo ""
    echo "WARNING: libsnowpack.a not found — check build output above"
    exit 1
fi
