from typing import ClassVar

import marshmallow as ma

from marshmallow_jsonschema.extensions import ReactJsonSchemaFormJSONSchema


class MySchema(ma.Schema):
    first_name = ma.fields.String(metadata={"ui:autofocus": True})
    last_name = ma.fields.String()

    class Meta:
        react_uischema_extra: ClassVar[dict[str, list[str]]] = {"ui:order": ["first_name", "last_name"]}


def test_can_dump_react_jsonschema_form():
    json_schema_obj = ReactJsonSchemaFormJSONSchema()
    json_schema, uischema = json_schema_obj.dump_with_uischema(MySchema())
    assert uischema == {
        "first_name": {"ui:autofocus": True},
        "last_name": {},
        "ui:order": ["first_name", "last_name"],
    }
    assert json_schema == {
        "$ref": "#/definitions/MySchema",
        "$schema": "http://json-schema.org/draft-07/schema#",
        "definitions": {
            "MySchema": {
                "additionalProperties": False,
                "properties": {
                    "first_name": {"title": "first_name", "type": "string", "ui:autofocus": True},
                    "last_name": {"title": "last_name", "type": "string"},
                },
                "type": "object",
            }
        },
    }
