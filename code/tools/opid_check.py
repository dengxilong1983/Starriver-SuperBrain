import json
import sys
import argparse
from pathlib import Path
from collections import defaultdict

# Ensure project root (code directory) is on sys.path so that `app` package can be imported when running this script directly
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

HTTP_METHODS = ("get","post","put","patch","delete","options","head","trace")

def load_spec_from_app() -> dict:
    from app.main import create_app
    app = create_app()
    spec = app.openapi()
    # Write latest schema snapshot
    with open(PROJECT_ROOT / "openapi_dump.json", "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False)
    return spec

def load_spec_from_file(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def check_operation_ids(spec: dict) -> tuple[int, int, dict]:
    by_id = defaultdict(list)
    paths = spec.get("paths") or {}
    for path, item in paths.items():
        item = item or {}
        for method, op in item.items():
            if (method or "").lower() not in HTTP_METHODS:
                continue
            op = op or {}
            oid = op.get("operationId")
            if not oid:
                print(f"[WARN] Missing operationId: {method.upper()} {path}")
                oid = f"missing__{method.lower()}__{path}"
            by_id[oid].append(f"{method.upper()} {path}")
    dups = {k:v for k,v in by_id.items() if len(v) > 1}
    total_ops = sum(len(v) for v in by_id.values())
    return total_ops, len(by_id), dups

def main() -> int:
    parser = argparse.ArgumentParser(description="OpenAPI operationId uniqueness checker")
    parser.add_argument("--input", "-i", type=str, default=None, help="Path to an existing OpenAPI JSON file; if omitted, generate from app")
    parser.add_argument("--fail-on-duplicates", action="store_true", help="Exit with non-zero code when duplicates are found")
    args = parser.parse_args()

    try:
        if args.input:
            spec_path = Path(args.input)
            if not spec_path.is_file():
                print(f"[ERROR] Input file not found: {spec_path}")
                return 1
            spec = load_spec_from_file(spec_path)
        else:
            spec = load_spec_from_app()
    except Exception as e:
        print(f"[ERROR] Failed to load OpenAPI spec: {e}")
        return 1

    total_ops, unique_count, dups = check_operation_ids(spec)
    print(f"Total operations: {total_ops}")
    print(f"Unique IDs: {unique_count}")
    print(f"Duplicates: {len(dups)}")
    if dups:
        print("Duplicate operationIds detected:")
        for k, v in dups.items():
            print(f"  - {k}: {', '.join(v)}")
        if args.fail_on_duplicates:
            return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())