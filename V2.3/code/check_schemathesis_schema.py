import traceback
import schemathesis
from app.main import create_app

app = create_app()

try:
    schema = schemathesis.from_asgi("/openapi.json", app)
    print("Schemathesis schema load: OK. Endpoints:", len(schema.get_all_endpoints()))
except Exception as e:
    print("Schemathesis schema load: FAILED")
    print("Exception type:", type(e))
    print("Exception repr:", repr(e))
    print("Exception str:", str(e))
    if getattr(e, "__cause__", None):
        print("Cause type:", type(e.__cause__))
        print("Cause repr:", repr(e.__cause__))
        print("Cause str:", str(e.__cause__))
    if getattr(e, "__context__", None):
        print("Context type:", type(e.__context__))
        print("Context repr:", repr(e.__context__))
        print("Context str:", str(e.__context__))
    traceback.print_exc()