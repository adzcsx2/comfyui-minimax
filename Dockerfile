ARG BASE_IMAGE=m.daocloud.io/docker.io/library/python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.source="https://github.com/adzcsx2/comfyui-minimax"
LABEL org.opencontainers.image.description="ComfyUI H3 Ref2VA with Fun ControlNet Union 2.0"

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple \
    HF_ENDPOINT=https://hf-mirror.com \
    COMFYUI_DIR=/opt/ComfyUI \
    VENV_DIR=/opt/venv \
    MODEL_DIR=/data/models \
    COMFYUI_LISTEN=0.0.0.0 \
    COMFYUI_PORT=6006

WORKDIR /opt/comfyui-minimax
COPY config/ config/
COPY scripts/ scripts/
COPY custom_nodes/ custom_nodes/
COPY workflows/ workflows/
COPY LICENSE NOTICE ./
RUN bash scripts/setup_apt.sh \
    && bash scripts/install_autodl.sh \
    && rm -rf /var/lib/apt/lists/* runtime/cache

EXPOSE 6006
VOLUME ["/data"]
HEALTHCHECK --start-period=180s --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6006/system_stats', timeout=4).close()"
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["bash", "scripts/start.sh"]
