#!/usr/bin/env bash
# Build (and optionally push) the h3-swap-worker image from docker/Dockerfile.
# Works from any directory: it always uses the repo root as the build context.
#
# Usage:
#   docker/build.sh [runtime|baked] [--tag TAG] [--push] [--platform PLATFORM]
#                   [--build-arg KEY=VALUE]...
#   docker/build.sh --help
#
# Targets:
#   runtime   (default) models are downloaded from R2 when the container boots.
#             Image is small. Use it on Salad (35 GB image limit).
#   baked     models are downloaded from R2 during the build. Needs the four R2
#             values in the environment (see below). Image is large. Use it on Vast.
#
# Options:
#   --tag TAG            image tag suffix, e.g. 0.1.0 (default: short git SHA, or "dev")
#   --push               docker push the image after a successful build
#   --platform PLATFORM  default linux/amd64
#   --build-arg K=V      forwarded to docker build; repeatable (e.g. COMFYUI_REF=<sha>)
#   -h, --help           show this text
#
# Environment:
#   IMAGE                registry/repo, default ghcr.io/YOUR_ORG/h3-swap-worker.
#                        Replace YOUR_ORG before --push; the script refuses the placeholder.
#
# Baked target: BuildKit secrets, read from the environment (never passed on the command line):
#   R2_ENDPOINT  R2_BUCKET  R2_ACCESS_KEY_ID  R2_SECRET_ACCESS_KEY
#   Each one becomes  --secret id=<lowercase name>,env=<NAME>. The Dockerfile mounts them
#   at /run/secrets/<id> for a single RUN step, so they never appear in an image layer.
#
# Login before --push (token from your own secret store, not from this repo):
#   echo "$GHCR_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USER --password-stdin
#
# Examples:
#   docker/build.sh runtime --tag 0.1.0 --push
#   export R2_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com R2_BUCKET=h3-swap
#   export R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=...
#   docker/build.sh baked --tag 0.1.0 --push
#
# UNVERIFIED: this script has not been run against a Docker daemon.

set -euo pipefail

readonly DEFAULT_IMAGE="ghcr.io/YOUR_ORG/h3-swap-worker"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPO_ROOT

usage() {
  cat <<'EOF'
Usage: docker/build.sh [runtime|baked] [--tag TAG] [--push] [--platform PLATFORM]
                       [--build-arg KEY=VALUE]...

  runtime   default; models fetched from R2 at container boot
  baked     models fetched from R2 at build time; needs R2_ENDPOINT, R2_BUCKET,
            R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY in the environment

Options: --tag TAG, --push, --platform PLATFORM (default linux/amd64),
         --build-arg KEY=VALUE (repeatable), -h/--help
Env:     IMAGE (default ghcr.io/YOUR_ORG/h3-swap-worker; set YOUR_ORG before --push)
EOF
}

TARGET="runtime"
TAG=""
PUSH=0
PLATFORM="linux/amd64"
BUILD_ARGS=()

while (( $# > 0 )); do
  case "$1" in
    runtime|baked) TARGET="$1" ;;
    --tag)
      TAG="${2:?--tag needs a value}"; shift ;;
    --push) PUSH=1 ;;
    --platform)
      PLATFORM="${2:?--platform needs a value}"; shift ;;
    --build-arg)
      BUILD_ARGS+=(--build-arg "${2:?--build-arg needs KEY=VALUE}"); shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

IMAGE="${IMAGE:-${DEFAULT_IMAGE}}"
if [[ -z "${TAG}" ]]; then
  TAG="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo dev)"
fi
REF="${IMAGE}:${TARGET}-${TAG}"

if (( PUSH )) && [[ "${IMAGE}" == *YOUR_ORG* ]]; then
  echo "refusing to push: IMAGE still has the YOUR_ORG placeholder (${IMAGE})" >&2
  exit 2
fi

SECRET_ARGS=()
if [[ "${TARGET}" == "baked" ]]; then
  for var in R2_ENDPOINT R2_BUCKET R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY; do
    if [[ -z "${!var:-}" ]]; then
      echo "baked target needs ${var} in the environment (value is not printed)" >&2
      exit 2
    fi
    SECRET_ARGS+=(--secret "id=${var,,},env=${var}")
  done
fi

export DOCKER_BUILDKIT=1

echo "building ${REF} (target=${TARGET}, platform=${PLATFORM})"
docker build \
  --file "${REPO_ROOT}/docker/Dockerfile" \
  --target "${TARGET}" \
  --platform "${PLATFORM}" \
  --tag "${REF}" \
  ${SECRET_ARGS[@]+"${SECRET_ARGS[@]}"} \
  ${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"} \
  "${REPO_ROOT}"

if (( PUSH )); then
  echo "pushing ${REF}"
  docker push "${REF}"
fi

echo "done: ${REF}"
