import importlib
import marshmallow_jsonschema

def test_import_marshmallow_enum(monkeypatch):
    monkeypatch.delattr("marshmallow_enum.EnumField")

    base = importlib.reload(marshmallow_jsonschema.base)

    assert not base.ALLOW_ENUMS

    monkeypatch.undo()

    importlib.reload(marshmallow_jsonschema.base)
