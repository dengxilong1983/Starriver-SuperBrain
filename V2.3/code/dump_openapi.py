from app.main import create_app
import json

app = create_app()

schema = app.openapi()
print("openapi_version:", schema.get("openapi"))
print("paths_count:", len(schema.get("paths", {})))

with open("_openapi_snapshot.json", "w", encoding="utf-8") as f:
    json.dump(schema, f, ensure_ascii=False, indent=2)
print("schema_written:_openapi_snapshot.json size:", len(json.dumps(schema)))