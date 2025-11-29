import sys
import types


# Minimal stubs for `google` namespaced packages to keep tests independent of
# installed google-cloud packages during unit testing. These stubs intentionally
# avoid implementing behavior and only provide placeholders for imports.
def _ensure_stub_module(name: str):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)


_ensure_stub_module("google")
_ensure_stub_module("google.api_core")
_ensure_stub_module("google.api_core.exceptions")
_ensure_stub_module("google.cloud")
_ensure_stub_module("google.cloud.firestore")
_ensure_stub_module("google.cloud.secretmanager")

# protobuf shim used by secret_store
_ensure_stub_module("google.protobuf")
_ensure_stub_module("google.protobuf.timestamp_pb2")
timestamp_mod = sys.modules["google.protobuf.timestamp_pb2"]


class Timestamp:
    def __init__(self):
        self._dt = None

    def FromDatetime(self, dt):
        self._dt = dt


setattr(timestamp_mod, "Timestamp", Timestamp)

# Provide minimal exception classes used by our code under test
exceptions_mod = sys.modules["google.api_core.exceptions"]
setattr(exceptions_mod, "NotFound", type("NotFound", (Exception,), {}))
setattr(exceptions_mod, "AlreadyExists", type("AlreadyExists", (Exception,), {}))
setattr(exceptions_mod, "GoogleAPICallError", type("GoogleAPICallError", (Exception,), {}))
