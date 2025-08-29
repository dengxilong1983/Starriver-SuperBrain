import os
import sys


def str_to_bool(val: str) -> bool:
    return str(val).lower() in {"1", "true", "yes", "y", "on"}


def main() -> None:
    try:
        import uvicorn
    except Exception as exc:
        print("[deploy] uvicorn 未安装，请先安装依赖: pip install -r requirements.txt", file=sys.stderr)
        raise

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    workers = int(os.getenv("WORKERS", "1"))
    reload = str_to_bool(os.getenv("RELOAD", "false"))
    log_level = os.getenv("LOG_LEVEL", "info")

    # 进程信息输出，便于在容器/本地环境观察
    print(
        f"[deploy] Starting FastAPI with uvicorn -> host={host} port={port} "
        f"workers={workers} reload={reload} log_level={log_level}",
        flush=True,
    )

    # 直接运行应用（支持单进程或多 worker）
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        workers=workers if not reload else 1,  # reload 模式禁用多 worker
        reload=reload,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()