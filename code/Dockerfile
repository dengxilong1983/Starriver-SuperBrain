# 移除 BuildKit 语法指令以兼容 legacy builder

FROM docker.m.daocloud.io/library/python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.2

WORKDIR /app

# 安装构建所需依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# 配置 pip 国内镜像源（清华）
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 复制依赖并安装
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app ./app
COPY data ./data
COPY scripts ./scripts

# 暴露默认端口
EXPOSE 8000

# 健康检查：使用 curl 以兼容 legacy builder（避免 heredoc）
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# 启动命令：可通过环境变量覆盖 HOST/PORT/WORKERS/RELOAD/LOG_LEVEL
ENV HOST=0.0.0.0 PORT=8000 WORKERS=1 RELOAD=false LOG_LEVEL=info
CMD ["python", "-m", "scripts.deploy"]

# ---- 测试阶段（仅用于CI/本地测试，不影响生产镜像）----
FROM base AS test
# 安装测试依赖（pytest、requests、httpx、pytest-cov、coverage）
RUN pip install --no-cache-dir -U pip pytest pytest-cov coverage requests httpx
# 复制测试代码
COPY tests ./tests
# 默认保持与base一致的工作目录与环境，运行时通过 `docker run <image> pytest -q` 覆盖命令