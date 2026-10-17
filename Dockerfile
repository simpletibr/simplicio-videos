# simplicio-video (issue #43): imagem local, sem publicação. ffmpeg e Node têm obrigações de licença; a imagem
# só é construída na sua máquina (docker compose build). Ver docs/host/packaging.md.
#
#   docker compose build
#   docker compose run --rm simplicio setup --yes
#   docker compose run --rm simplicio doctor
#
# A imagem instala o pacote por pip (a distribuição `pip`). `scripts/dev_install.sh` é o .venv do checkout e não roda aqui, e o
# `simplicio-video install` (que copia a skill para o host de um agente) não tem o que fazer num contêiner. O `simplicio-video update`
# de um pacote faria um pip install dentro da imagem: para atualizar, reconstrua a imagem (docker compose build).

# Node 22 vem de uma imagem oficial pinada por tag (o render do HyperFrames precisa de Node).
FROM node:22-bookworm-slim AS node

# Stage de build: dependências Python instaladas num venv que é copiado para a imagem final.
FROM python:3.12-slim-bookworm AS build
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY pyproject.toml PYPI.md LICENSE NOTICE ./
COPY src ./src
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install .

# Imagem final: Python 3.12, ffmpeg (com libass, do Debian), Node 22 e um usuário sem root.
FROM python:3.12-slim-bookworm AS final
ENV PATH="/opt/venv/bin:${PATH}" \
    SIMPLICIO_WORKSPACE=/workspace \
    PYTHONUNBUFFERED=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
COPY --from=build /opt/venv /opt/venv
RUN groupadd --system --gid 10001 simplicio \
 && useradd --system --uid 10001 --gid simplicio --create-home --home-dir /home/simplicio simplicio \
 && mkdir -p /workspace \
 && chown simplicio:simplicio /workspace
USER simplicio
# The work folder IS the volume: `init` writes ./clients/<client>/<campaign>/contract.yaml in the cwd, and anything
# outside /workspace is lost with `docker compose run --rm`.
WORKDIR /workspace
VOLUME ["/workspace"]
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD ["simplicio-video", "--version"]
ENTRYPOINT ["simplicio-video"]
CMD ["--help"]
