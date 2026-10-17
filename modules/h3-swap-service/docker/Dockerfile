# syntax=docker/dockerfile:1.7
#
# h3-swap-worker image: ComfyUI (headless) + custom nodes + worker/ + model fetcher.
#
# UNVERIFIED: this file has not been built. No Docker daemon with GPU and BuildKit
# was available when it was written. See docker/README_docker.md for the VERIFY list.
#
# Build from the REPO ROOT (the build context must contain worker/ and docker/):
#   docker build -f docker/Dockerfile --target runtime -t ghcr.io/YOUR_ORG/h3-swap-worker:runtime .
#   docker build -f docker/Dockerfile --target baked \
#     --secret id=r2_endpoint,env=R2_ENDPOINT --secret id=r2_bucket,env=R2_BUCKET \
#     --secret id=r2_access_key_id,env=R2_ACCESS_KEY_ID \
#     --secret id=r2_secret_access_key,env=R2_SECRET_ACCESS_KEY \
#     -t ghcr.io/YOUR_ORG/h3-swap-worker:baked .
#
# Targets:
#   runtime  (default, last stage) model weights are downloaded from R2 when the container boots.
#   baked    model weights are downloaded from R2 during `docker build` using BuildKit secrets.
#            Secrets are mounted for one RUN only and never written to a layer or ARG.
#
# Both targets fetch config/workflow_api.json and config/workflow_map.json from R2 at every
# boot (not at build time), so a workflow change needs no image rebuild.
# The worker starts with `python -m worker` (worker/__main__.py), called from entrypoint.sh.

# VERIFY tag exists on Docker Hub (nvidia/cuda, 13.0.0 runtime, ubuntu24.04).
ARG BASE_IMAGE=nvidia/cuda:13.0.0-runtime-ubuntu24.04
# VERIFY the cu130 index and torch versions. The Comfy-Org card recommends the int8_convrot
# diffusion models "if you are able to use pytorch with cu130", so the cu130 index is kept
# for that path. The card says nothing about a GPU model requirement.
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu130
ARG TORCH_PACKAGES="torch torchvision torchaudio"
ARG BOTO3_SPEC="boto3>=1.34,<2"

# ComfyUI and custom nodes. Prefer full commit SHAs for production builds (VERIFY).
ARG COMFYUI_REPO=https://github.com/comfyanonymous/ComfyUI.git
ARG COMFYUI_REF=master
ARG H3_CONTINUUM_REPO=https://github.com/wesleysimplicio/comfyui-h3-continuum.git
ARG H3_CONTINUUM_REF=main
ARG RGTHREE_REPO=https://github.com/rgthree/rgthree-comfy.git
ARG RGTHREE_REF=main
ARG KJNODES_REPO=https://github.com/kijai/ComfyUI-KJNodes.git
ARG KJNODES_REF=main

# ---------------------------------------------------------------------------
# base: OS packages, venv, torch (cu130), boto3
# ---------------------------------------------------------------------------
FROM ${BASE_IMAGE} AS base
ARG TORCH_INDEX_URL
ARG TORCH_PACKAGES
ARG BOTO3_SPEC

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:${PATH}

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv git ffmpeg curl aria2 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# VERIFY: Ubuntu 24.04 ships Python 3.12 as python3. Code targets 3.11 syntax and runs on 3.12.
RUN python3 -m venv /opt/venv \
 && pip install --upgrade pip wheel

# VERIFY: torch wheels on this index are built for CUDA 13.0 (cu130).
RUN pip install --index-url "${TORCH_INDEX_URL}" ${TORCH_PACKAGES}

# Pin the installed torch stack for every later pip call (ComfyUI and node
# requirements list an unpinned torch; this stops pip from swapping in PyPI wheels).
RUN pip freeze | grep -E '^(torch|torchvision|torchaudio)==' > /opt/torch-constraints.txt \
 && cat /opt/torch-constraints.txt
ENV PIP_CONSTRAINT=/opt/torch-constraints.txt

RUN pip install "${BOTO3_SPEC}"

# ---------------------------------------------------------------------------
# comfy: ComfyUI + custom nodes
# ---------------------------------------------------------------------------
FROM base AS comfy
ARG COMFYUI_REPO
ARG COMFYUI_REF
ARG H3_CONTINUUM_REPO
ARG H3_CONTINUUM_REF
ARG RGTHREE_REPO
ARG RGTHREE_REF
ARG KJNODES_REPO
ARG KJNODES_REF

RUN git clone --filter=blob:none "${COMFYUI_REPO}" /opt/ComfyUI \
 && git -C /opt/ComfyUI checkout "${COMFYUI_REF}" \
 && pip install -r /opt/ComfyUI/requirements.txt

RUN git clone --filter=blob:none "${H3_CONTINUUM_REPO}" /opt/ComfyUI/custom_nodes/comfyui-h3-continuum \
 && git -C /opt/ComfyUI/custom_nodes/comfyui-h3-continuum checkout "${H3_CONTINUUM_REF}" \
 && if [ -f /opt/ComfyUI/custom_nodes/comfyui-h3-continuum/requirements.txt ]; then \
      pip install -r /opt/ComfyUI/custom_nodes/comfyui-h3-continuum/requirements.txt; \
    fi

RUN git clone --filter=blob:none "${RGTHREE_REPO}" /opt/ComfyUI/custom_nodes/rgthree-comfy \
 && git -C /opt/ComfyUI/custom_nodes/rgthree-comfy checkout "${RGTHREE_REF}" \
 && if [ -f /opt/ComfyUI/custom_nodes/rgthree-comfy/requirements.txt ]; then \
      pip install -r /opt/ComfyUI/custom_nodes/rgthree-comfy/requirements.txt; \
    fi

RUN git clone --filter=blob:none "${KJNODES_REPO}" /opt/ComfyUI/custom_nodes/ComfyUI-KJNodes \
 && git -C /opt/ComfyUI/custom_nodes/ComfyUI-KJNodes checkout "${KJNODES_REF}" \
 && if [ -f /opt/ComfyUI/custom_nodes/ComfyUI-KJNodes/requirements.txt ]; then \
      pip install -r /opt/ComfyUI/custom_nodes/ComfyUI-KJNodes/requirements.txt; \
    fi

# ---------------------------------------------------------------------------
# app: worker package, entrypoint, model fetcher
# ---------------------------------------------------------------------------
FROM comfy AS app
WORKDIR /app

# worker/ is owned by squad B and must provide requirements.txt.
# Workflow files are NOT copied here: entrypoint.sh fetches them from R2 (config/) at boot.
COPY worker/ /app/worker/
RUN pip install -r /app/worker/requirements.txt

COPY --chmod=0755 docker/entrypoint.sh /app/entrypoint.sh
COPY docker/fetch_models.py /app/fetch_models.py
COPY docker/models.manifest.json /app/models.manifest.json

ENTRYPOINT ["/app/entrypoint.sh"]

# ---------------------------------------------------------------------------
# baked: models downloaded at build time (Vast: the loading phase is not billed)
# ---------------------------------------------------------------------------
FROM app AS baked
ENV MODELS_MODE=baked
# Each secret is read from /run/secrets inside this RUN only. The values are
# exported for this shell and are gone after the step. Nothing lands in a layer.
RUN --mount=type=secret,id=r2_endpoint \
    --mount=type=secret,id=r2_bucket \
    --mount=type=secret,id=r2_access_key_id \
    --mount=type=secret,id=r2_secret_access_key \
    sh -eu -c '\
      R2_ENDPOINT="$(cat /run/secrets/r2_endpoint)"; export R2_ENDPOINT; \
      R2_BUCKET="$(cat /run/secrets/r2_bucket)"; export R2_BUCKET; \
      R2_ACCESS_KEY_ID="$(cat /run/secrets/r2_access_key_id)"; export R2_ACCESS_KEY_ID; \
      R2_SECRET_ACCESS_KEY="$(cat /run/secrets/r2_secret_access_key)"; export R2_SECRET_ACCESS_KEY; \
      python /app/fetch_models.py --manifest /app/models.manifest.json --models-dir /opt/ComfyUI/models --scope models'
# --scope models: build-time fetch covers the required weights only. Config is fetched at every
# boot, and optional alternatives (required=false) are never baked; they are runtime-only (FETCH_OPTIONAL).

# ---------------------------------------------------------------------------
# runtime: models downloaded from R2 at boot (default target: must stay last)
# ---------------------------------------------------------------------------
FROM app AS runtime
ENV MODELS_MODE=runtime
