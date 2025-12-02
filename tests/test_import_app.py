def test_import_app():
    import importlib
    import os
    import sys

    # Ensure repo root is on PYTHONPATH so imports like `app` work during test run
    sys.path.insert(0, os.getcwd())

    main = importlib.import_module("app.main")
    assert hasattr(main, "app")
