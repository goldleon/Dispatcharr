#!/bin/bash

# scripts/build_prod_aio.sh
# Build and Push Dispatcharr Production AIO Image (Multi-arch)

set -e

# Default values
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION=$(python3 -c "import sys; sys.path.append('${ROOT_DIR}'); import version; print(version.__version__)")
REGISTRY="docker.io"
ORG="dispatcharr"
IMAGE="dispatcharr"
PLATFORMS="linux/amd64,linux/arm64"
TIMESTAMP=$(date -u +'%Y%m%d%H%M%S')

usage() {
    cat <<-EOF
Usage: $0 [options]

Build and Push Dispatcharr Production AIO Image (Multi-arch)

Options:
  -o ORG       Docker Hub Organization (default: dispatcharr)
  -i IMAGE     Image name (default: dispatcharr)
  -p PLATFORMS Architectures to build (default: linux/amd64,linux/arm64)
  -n           No push (build only)
  -h           Show this help
EOF
    exit 0
}

PUSH=true

while getopts "o:i:p:nh" opt; do
    case $opt in
        o) ORG="$OPTARG" ;;
        i) IMAGE="$OPTARG" ;;
        p) PLATFORMS="$OPTARG" ;;
        n) PUSH=false ;;
        h) usage ;;
        \?) exit 1 ;;
    esac
done

FULL_IMAGE="${REGISTRY}/${ORG}/${IMAGE}"

echo "🚀 Building Dispatcharr Production AIO Image"
echo "📦 Version:   ${VERSION}"
echo "🕒 Timestamp: ${TIMESTAMP}"
echo "🌍 Target:    ${FULL_IMAGE}"
echo "🖥️ Platforms: ${PLATFORMS}"

# Buildx arguments
BUILDX_ARGS="--platform ${PLATFORMS} \
    --build-arg TIMESTAMP=${TIMESTAMP} \
    --build-arg REPO_OWNER=dispatcharr \
    --build-arg REPO_NAME=dispatcharr \
    --build-arg BRANCH=main"

if [ "$PUSH" = "true" ]; then
    echo "📤 Push enabled"
    docker buildx build ${BUILDX_ARGS} \
        -f "${ROOT_DIR}/docker/Dockerfile" \
        -t "${FULL_IMAGE}:latest" \
        -t "${FULL_IMAGE}:${VERSION}" \
        -t "${FULL_IMAGE}:v${VERSION}" \
        --push \
        "${ROOT_DIR}"
else
    echo "🛠️ Build only (load to local if single platform, otherwise just verify)"
    # Note: multi-arch cannot be 'loaded' to local docker daemon easily without a registry.
    # We use --output=type=image for verification.
    docker buildx build ${BUILDX_ARGS} \
        -f "${ROOT_DIR}/docker/Dockerfile" \
        -t "${IMAGE}:test" \
        "${ROOT_DIR}"
fi

echo "✅ Build complete!"
