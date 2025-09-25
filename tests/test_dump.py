import uuid
from dataclasses import dataclass
from enum import Enum

import pytest
from marshmallow import Schema, fields, validate
from marshmallow_dataclass import class_schema
from marshmallow_enum import EnumField as MarshmallowEnumEnumField
from marshmallow_union import Union

import marshmallow_jsonschema
from marshmallow_jsonschema import JSONSchema, UnsupportedValueError

from . import UserSchema, validate_and_dump

TEST_MARSHMALLOW_NATIVE_ENUM = marshmallow_jsonschema.base.marshmallow_version_supports_native_enums()
try:
    from marshmallow.fields import Enum as MarshmallowNativeEnumField
except ImportError:
    assert TEST_MARSHMALLOW_NATIVE_ENUM is False


def test_dump_schema():
    schema = UserSchema()

    dumped = validate_and_dump(schema)

    assert len(schema.fields) > 1

    props = dumped["definitions"]["UserSchema"]["properties"]
    for field_name in schema.fields:
        assert field_name in props


def test_default():
    schema = UserSchema()

    dumped = validate_and_dump(schema)

    props = dumped["definitions"]["UserSchema"]["properties"]
    assert props["id"]["default"] == "no-id"


def test_default_callable_not_serialized():
    class TestSchema(Schema):
        uid = fields.UUID(default=uuid.uuid4)

    schema = TestSchema()

    dumped = validate_and_dump(schema)

    props = dumped["definitions"]["TestSchema"]["properties"]
    assert "default" not in props["uid"]


def test_uuid():
    schema = UserSchema()

    dumped = validate_and_dump(schema)

    props = dumped["definitions"]["UserSchema"]["properties"]
    assert props["uid"]["type"] == "string"
    assert props["uid"]["format"] == "uuid"


def test_metadata():
    """Metadata should be available in the field definition."""

    class TestSchema(Schema):
        myfield = fields.String(metadata={"foo": "Bar"})
        yourfield = fields.Integer(required=True, baz="waz")

    schema = TestSchema()

    dumped = validate_and_dump(schema)

    props = dumped["definitions"]["TestSchema"]["properties"]
    assert props["myfield"]["foo"] == "Bar"
    assert props["yourfield"]["baz"] == "waz"
    assert "metadata" not in props["myfield"]
    assert "metadata" not in props["yourfield"]

    # repeat process to assert idempotency
    dumped = validate_and_dump(schema)

    props = dumped["definitions"]["TestSchema"]["properties"]
    assert props["myfield"]["foo"] == "Bar"
    assert props["yourfield"]["baz"] == "waz"


def test_descriptions():
    class TestSchema(Schema):
        myfield = fields.String(metadata={"description": "Brown Cow"})
        yourfield = fields.Integer(required=True)

    schema = TestSchema()

    dumped = validate_and_dump(schema)

    props = dumped["definitions"]["TestSchema"]["properties"]
    assert props["myfield"]["description"] == "Brown Cow"


def test_nested_descriptions():
    class TestNestedSchema(Schema):
        myfield = fields.String(metadata={"description": "Brown Cow"})
        yourfield = fields.Integer(required=True)

    class TestSchema(Schema):
        nested = fields.Nested(TestNestedSchema, metadata={"description": "Nested 1", "title": "Title1"})
        yourfield_nested = fields.Integer(required=True)

    schema = TestSchema()

    dumped = validate_and_dump(schema)

    nested_def = dumped["definitions"]["TestNestedSchema"]
    nested_dmp = dumped["definitions"]["TestSchema"]["properties"]["nested"]
    assert nested_def["properties"]["myfield"]["description"] == "Brown Cow"

    assert nested_dmp["$ref"] == "#/definitions/TestNestedSchema"
    assert nested_dmp["description"] == "Nested 1"
    assert nested_dmp["title"] == "Title1"


def test_nested_string_to_cls():
    class TestNamedNestedSchema(Schema):
        foo = fields.Integer(required=True)

    class TestSchema(Schema):
        foo2 = fields.Integer(required=True)
        nested = fields.Nested("TestNamedNestedSchema")

    schema = TestSchema()

    dumped = validate_and_dump(schema)

    nested_def = dumped["definitions"]["TestNamedNestedSchema"]
    nested_dmp = dumped["definitions"]["TestSchema"]["properties"]["nested"]
    assert nested_dmp["type"] == "object"
    assert nested_def["properties"]["foo"]["type"] == "integer"


def test_nested_context():
    class TestNestedSchema(Schema):
        def __init__(self, *args, **kwargs):
            if kwargs.get("context", {}).get("hide", False):
                kwargs["exclude"] = ["foo"]
            super().__init__(*args, **kwargs)

        foo = fields.Integer(required=True)
        bar = fields.Integer(required=True)

    class TestSchema(Schema):
        bar = fields.Nested(TestNestedSchema)

    schema = TestSchema()
    dumped_show = validate_and_dump(schema)

    schema = TestSchema(context={"hide": True})
    dumped_hide = validate_and_dump(schema)

    nested_show = dumped_show["definitions"]["TestNestedSchema"]["properties"]
    nested_hide = dumped_hide["definitions"]["TestNestedSchema"]["properties"]

    assert "bar" in nested_show
    assert "foo" in nested_show
    assert "bar" in nested_hide
    assert "foo" not in nested_hide


def test_list():
    class ListSchema(Schema):
        foo = fields.List(fields.String(), required=True)

    schema = ListSchema()
    dumped = validate_and_dump(schema)

    nested_json = dumped["definitions"]["ListSchema"]["properties"]["foo"]
    assert nested_json["type"] == "array"
    assert "items" in nested_json

    item_schema = nested_json["items"]
    assert item_schema["type"] == "string"


def test_list_nested():
    """Test that a list field will work with an inner nested field."""

    class InnerSchema(Schema):
        foo = fields.Integer(required=True)

    class ListSchema(Schema):
        bar = fields.List(fields.Nested(InnerSchema), required=True)

    schema = ListSchema()
    dumped = validate_and_dump(schema)

    nested_json = dumped["definitions"]["ListSchema"]["properties"]["bar"]

    assert nested_json["type"] == "array"
    assert "items" in nested_json

    item_schema = nested_json["items"]
    assert "InnerSchema" in item_schema["$ref"]


def test_dict():
    class DictSchema(Schema):
        foo = fields.Dict()

    schema = DictSchema()
    dumped = validate_and_dump(schema)

    nested_json = dumped["definitions"]["DictSchema"]["properties"]["foo"]

    assert nested_json["type"] == "object"
    assert "additionalProperties" in nested_json

    item_schema = nested_json["additionalProperties"]
    assert item_schema == {}


def test_dict_with_value_field():
    class DictSchema(Schema):
        foo = fields.Dict(keys=fields.String, values=fields.Integer)

    schema = DictSchema()
    dumped = validate_and_dump(schema)

    nested_json = dumped["definitions"]["DictSchema"]["properties"]["foo"]

    assert nested_json["type"] == "object"
    assert "additionalProperties" in nested_json

    item_schema = nested_json["additionalProperties"]
    assert item_schema["type"] == "integer"


def test_dict_with_nested_value_field():
    class InnerSchema(Schema):
        foo = fields.Integer(required=True)

    class DictSchema(Schema):
        bar = fields.Dict(keys=fields.String, values=fields.Nested(InnerSchema))

    schema = DictSchema()
    dumped = validate_and_dump(schema)

    nested_json = dumped["definitions"]["DictSchema"]["properties"]["bar"]

    assert nested_json["type"] == "object"
    assert "additionalProperties" in nested_json

    item_schema = nested_json["additionalProperties"]
    assert item_schema["type"] == "object"

    assert "InnerSchema" in item_schema["$ref"]


def test_deep_nested():
    """Test that deep nested schemas are in definitions."""

    class InnerSchema(Schema):
        boz = fields.Integer(required=True)

    class InnerMiddleSchema(Schema):
        baz = fields.Nested(InnerSchema, required=True)

    class OuterMiddleSchema(Schema):
        bar = fields.Nested(InnerMiddleSchema, required=True)

    class OuterSchema(Schema):
        foo = fields.Nested(OuterMiddleSchema, required=True)

    schema = OuterSchema()
    dumped = validate_and_dump(schema)

    defs = dumped["definitions"]
    assert "OuterSchema" in defs
    assert "OuterMiddleSchema" in defs
    assert "InnerMiddleSchema" in defs
    assert "InnerSchema" in defs


def test_respect_only_for_nested_schema():
    """Should ignore fields not in 'only' metadata for nested schemas."""

    class InnerRecursiveSchema(Schema):
        id = fields.Integer(required=True)
        baz = fields.String()
        recursive = fields.Nested("InnerRecursiveSchema")

    class MiddleSchema(Schema):
        id = fields.Integer(required=True)
        bar = fields.String()
        inner = fields.Nested("InnerRecursiveSchema", only=("id", "baz"))

    class OuterSchema(Schema):
        foo2 = fields.Integer(required=True)
        nested = fields.Nested("MiddleSchema")

    schema = OuterSchema()
    dumped = validate_and_dump(schema)
    inner_props = dumped["definitions"]["InnerRecursiveSchema"]["properties"]
    assert "recursive" not in inner_props


def test_respect_exclude_for_nested_schema():
    """Should ignore fields in 'exclude' metadata for nested schemas."""

    class InnerRecursiveSchema(Schema):
        id = fields.Integer(required=True)
        baz = fields.String()
        recursive = fields.Nested("InnerRecursiveSchema")

    class MiddleSchema(Schema):
        id = fields.Integer(required=True)
        bar = fields.String()
        inner = fields.Nested("InnerRecursiveSchema", exclude=("recursive",))

    class OuterSchema(Schema):
        foo2 = fields.Integer(required=True)
        nested = fields.Nested("MiddleSchema")

    schema = OuterSchema()

    dumped = validate_and_dump(schema)

    inner_props = dumped["definitions"]["InnerRecursiveSchema"]["properties"]
    assert "recursive" not in inner_props


def test_respect_dotted_exclude_for_nested_schema():
    """Should ignore dotted fields in 'exclude' metadata for nested schemas."""

    class InnerRecursiveSchema(Schema):
        id = fields.Integer(required=True)
        baz = fields.String()
        recursive = fields.Nested("InnerRecursiveSchema")

    class MiddleSchema(Schema):
        id = fields.Integer(required=True)
        bar = fields.String()
        inner = fields.Nested("InnerRecursiveSchema")

    class OuterSchema(Schema):
        foo2 = fields.Integer(required=True)
        nested = fields.Nested("MiddleSchema", exclude=("inner.recursive",))

    schema = OuterSchema()

    dumped = validate_and_dump(schema)

    inner_props = dumped["definitions"]["InnerRecursiveSchema"]["properties"]
    assert "recursive" not in inner_props


def test_respect_default_for_nested_schema():
    class TestNestedSchema(Schema):
        myfield = fields.String()
        yourfield = fields.Integer(required=True)

    nested_default = {"myfield": "myval", "yourfield": 1}

    class TestSchema(Schema):
        nested = fields.Nested(
            TestNestedSchema,
            default=nested_default,
        )
        yourfield_nested = fields.Integer(required=True)

    schema = TestSchema()
    dumped = validate_and_dump(schema)
    default = dumped["definitions"]["TestSchema"]["properties"]["nested"]["default"]
    assert default == nested_default


def test_nested_instance():
    """Should also work with nested schema instances"""

    class TestNestedSchema(Schema):
        baz = fields.Integer()

    class TestSchema(Schema):
        foo = fields.String()
        bar = fields.Nested(TestNestedSchema())

    schema = TestSchema()

    dumped = validate_and_dump(schema)

    nested_def = dumped["definitions"]["TestNestedSchema"]
    nested_obj = dumped["definitions"]["TestSchema"]["properties"]["bar"]

    assert "baz" in nested_def["properties"]
    assert nested_obj["$ref"] == "#/definitions/TestNestedSchema"


def test_function():
    """Function fields can be serialised if type is given."""

    class FnSchema(Schema):
        fn_str = fields.Function(lambda: "string", required=True, _jsonschema_type_mapping={"type": "string"})
        fn_int = fields.Function(lambda: 123, required=True, _jsonschema_type_mapping={"type": "number"})

    schema = FnSchema()

    dumped = validate_and_dump(schema)

    props = dumped["definitions"]["FnSchema"]["properties"]
    assert props["fn_int"]["type"] == "number"
    assert props["fn_str"]["type"] == "string"


def test_nested_recursive():
    """A self-referential schema should not cause an infinite recurse."""

    class RecursiveSchema(Schema):
        foo = fields.Integer(required=True)
        children = fields.Nested("RecursiveSchema", many=True)

    schema = RecursiveSchema()

    dumped = validate_and_dump(schema)

    props = dumped["definitions"]["RecursiveSchema"]["properties"]
    assert "RecursiveSchema" in props["children"]["items"]["$ref"]


def test_title():
    class TestSchema(Schema):
        myfield = fields.String(metadata={"title": "Brown Cowzz"})
        yourfield = fields.Integer(required=True)

    schema = TestSchema()

    dumped = validate_and_dump(schema)

    assert dumped["definitions"]["TestSchema"]["properties"]["myfield"]["title"] == "Brown Cowzz"


def test_unknown_typed_field_throws_valueerror():
    class Invalid(fields.Field):
        def _serialize(self, value, _attr, _obj):
            return value

    class UserSchema(Schema):
        favourite_colour = Invalid()

    schema = UserSchema()
    json_schema = JSONSchema()

    with pytest.raises(UnsupportedValueError):
        validate_and_dump(json_schema.dump(schema))


def test_unknown_typed_field():
    class Colour(fields.Field):
        def _jsonschema_type_mapping(self):
            return {"type": "string"}

        def _serialize(self, value, _attr, _obj):
            r, g, b = value
            return f"#{r:x}{g:x}{b:x}"

    class UserSchema(Schema):
        name = fields.String(required=True)
        favourite_colour = Colour()

    schema = UserSchema()

    dumped = validate_and_dump(schema)

    assert dumped["definitions"]["UserSchema"]["properties"]["favourite_colour"] == {"type": "string"}


def test_field_subclass():
    """JSON schema generation should not fail on sublcass marshmallow field."""

    class CustomField(fields.Field):
        pass

    class TestSchema(Schema):
        myfield = CustomField()

    schema = TestSchema()
    with pytest.raises(UnsupportedValueError):
        _ = validate_and_dump(schema)


def test_readonly():
    class TestSchema(Schema):
        id = fields.Integer(required=True)
        readonly_fld = fields.String(dump_only=True)

    schema = TestSchema()

    dumped = validate_and_dump(schema)

    assert dumped["definitions"]["TestSchema"]["properties"]["readonly_fld"] == {
        "title": "readonly_fld",
        "type": "string",
        "readOnly": True,
    }


def test_metadata_direct_from_field():
    """Should be able to get metadata without accessing metadata kwarg."""

    class TestSchema(Schema):
        id = fields.Integer(required=True)
        metadata_field = fields.String(description="Directly on the field!")

    schema = TestSchema()

    dumped = validate_and_dump(schema)

    assert dumped["definitions"]["TestSchema"]["properties"]["metadata_field"] == {
        "title": "metadata_field",
        "type": "string",
        "description": "Directly on the field!",
    }


def test_allow_none():
    """A field with allow_none set to True should have type null as additional."""

    class TestSchema(Schema):
        id = fields.Integer(required=True)
        readonly_fld = fields.String(allow_none=True)

    schema = TestSchema()

    dumped = validate_and_dump(schema)

    assert dumped["definitions"]["TestSchema"]["properties"]["readonly_fld"] == {
        "title": "readonly_fld",
        "type": ["string", "null"],
    }


def test_dumps_iterable_enums():
    mapping = {"a": 0, "b": 1, "c": 2}

    class TestSchema(Schema):
        foo = fields.Integer(validate=validate.OneOf(mapping.values(), labels=mapping.keys()))

    schema = TestSchema()

    dumped = validate_and_dump(schema)

    assert dumped["definitions"]["TestSchema"]["properties"]["foo"] == {
        "oneOf": [{"type": "integer", "title": k, "const": v} for k, v in mapping.items()],
        "title": "foo",
        "type": "integer",
    }


def test_required_excluded_when_empty():
    class TestSchema(Schema):
        optional_value = fields.String()

    schema = TestSchema()

    dumped = validate_and_dump(schema)

    assert "required" not in dumped["definitions"]["TestSchema"]


def test_required_uses_data_key():
    class TestSchema(Schema):
        optional_value = fields.String(data_key="opt", required=True)

    schema = TestSchema()

    dumped = validate_and_dump(schema)

    test_schema_definition = dumped["definitions"]["TestSchema"]
    assert "opt" in test_schema_definition["properties"]
    assert test_schema_definition["properties"]["opt"]["title"] == "optional_value"
    assert "required" in test_schema_definition
    assert "opt" in test_schema_definition["required"]


def test_datetime_based():
    class TestSchema(Schema):
        f_date = fields.Date()
        f_datetime = fields.DateTime()
        f_time = fields.Time()

    schema = TestSchema()

    dumped = validate_and_dump(schema)

    assert dumped["definitions"]["TestSchema"]["properties"]["f_date"] == {
        "format": "date",
        "title": "f_date",
        "type": "string",
    }

    assert dumped["definitions"]["TestSchema"]["properties"]["f_datetime"] == {
        "format": "date-time",
        "title": "f_datetime",
        "type": "string",
    }

    assert dumped["definitions"]["TestSchema"]["properties"]["f_time"] == {
        "format": "time",
        "title": "f_time",
        "type": "string",
    }


def test_sorting_properties():
    class TestSchema(Schema):
        class Meta:
            ordered = True

        d = fields.Str()
        c = fields.Str()
        a = fields.Str()

    # Should be sorting of fields
    schema = TestSchema()

    json_schema = JSONSchema()
    data = json_schema.dump(schema)

    sorted_keys = sorted(data["definitions"]["TestSchema"]["properties"].keys())
    assert list(sorted_keys) == ["a", "c", "d"]

    # Should be saving ordering of fields
    schema = TestSchema()

    json_schema = JSONSchema(props_ordered=True)
    data = json_schema.dump(schema)

    keys = data["definitions"]["TestSchema"]["properties"].keys()

    assert list(keys) == ["d", "c", "a"]


def test_marshmallow_enum_enum_based():
    class TestEnum(Enum):
        value_1 = 0
        value_2 = 1
        value_3 = 2

    class TestSchema(Schema):
        enum_prop = MarshmallowEnumEnumField(TestEnum)

    # Should be sorting of fields
    schema = TestSchema()

    json_schema = JSONSchema()
    data = json_schema.dump(schema)

    assert data["definitions"]["TestSchema"]["properties"]["enum_prop"]["type"] == "string"
    received_enum_values = sorted(data["definitions"]["TestSchema"]["properties"]["enum_prop"]["enum"])
    assert received_enum_values == ["value_1", "value_2", "value_3"]


def test_native_marshmallow_enum_based():
    if not TEST_MARSHMALLOW_NATIVE_ENUM:
        return

    class TestEnum(Enum):
        value_1 = 0
        value_2 = 1
        value_3 = 2

    class TestSchema(Schema):
        enum_prop = MarshmallowNativeEnumField(TestEnum)

    # Should be sorting of fields
    schema = TestSchema()

    json_schema = JSONSchema()
    data = json_schema.dump(schema)

    assert data["definitions"]["TestSchema"]["properties"]["enum_prop"]["type"] == "string"
    received_enum_values = sorted(data["definitions"]["TestSchema"]["properties"]["enum_prop"]["enum"])
    assert received_enum_values == ["value_1", "value_2", "value_3"]


def test_marshmallow_enum_enum_based_load_dump_value():
    class TestEnum(Enum):
        value_1 = 0
        value_2 = 1
        value_3 = 2

    class TestSchema(Schema):
        enum_prop = MarshmallowEnumEnumField(TestEnum, by_value=True)

    # Should be sorting of fields
    schema = TestSchema()

    json_schema = JSONSchema()

    with pytest.raises(NotImplementedError):
        validate_and_dump(json_schema.dump(schema))


def test_native_marshmallow_enum_based_load_dump_value():
    if not TEST_MARSHMALLOW_NATIVE_ENUM:
        return

    class TestEnum(Enum):
        value_1 = 0
        value_2 = 1
        value_3 = 2

    class TestSchema(Schema):
        enum_prop = MarshmallowNativeEnumField(TestEnum, by_value=True)

    # Should be sorting of fields
    schema = TestSchema()

    json_schema = JSONSchema()

    with pytest.raises(NotImplementedError):
        validate_and_dump(json_schema.dump(schema))


def test_union_based():
    class TestNestedSchema(Schema):
        field_1 = fields.String()
        field_2 = fields.Integer()

    class TestSchema(Schema):
        union_prop = Union([fields.String(), fields.Integer(), fields.Nested(TestNestedSchema)])

    # Should be sorting of fields
    schema = TestSchema()

    json_schema = JSONSchema()
    data = json_schema.dump(schema)

    # Expect only the `anyOf` key
    assert "anyOf" in data["definitions"]["TestSchema"]["properties"]["union_prop"]
    assert len(data["definitions"]["TestSchema"]["properties"]["union_prop"]) == 1

    string_schema = {"type": "string", "title": ""}
    integer_schema = {"type": "string", "title": ""}
    referenced_nested_schema = {
        "type": "object",
        "$ref": "#/definitions/TestNestedSchema",
    }
    actual_nested_schema = {
        "type": "object",
        "properties": {
            "field_1": {"type": "string", "title": "field_1"},
            "field_2": {"type": "integer", "title": "field_2"},
        },
        "additionalProperties": False,
    }

    assert string_schema in data["definitions"]["TestSchema"]["properties"]["union_prop"]["anyOf"]
    assert integer_schema in data["definitions"]["TestSchema"]["properties"]["union_prop"]["anyOf"]
    assert referenced_nested_schema in data["definitions"]["TestSchema"]["properties"]["union_prop"]["anyOf"]

    assert data["definitions"]["TestNestedSchema"] == actual_nested_schema
    # Expect three possible schemas for the union type
    assert len(data["definitions"]["TestSchema"]["properties"]["union_prop"]["anyOf"]) == 3


def test_dumping_recursive_schema():
    """
    this reproduces issue https://github.com/fuhrysteve/marshmallow-jsonschema/issues/164
    """
    json_schema = JSONSchema()

    def generate_recursive_schema_with_name():
        class RecursiveSchema(Schema):
            # when nesting recursively you can either refer the recursive schema by its name
            nested_mwe_recursive = fields.Nested("RecursiveSchema")

        return json_schema.dump(RecursiveSchema())

    def generate_recursive_schema_with_lambda():
        class RecursiveSchema(Schema):
            # or you can use a lambda (as suggested in the marshmallow docs)
            nested_mwe_recursive = fields.Nested(lambda: RecursiveSchema())

        return json_schema.dump(RecursiveSchema())  # this shall _not_ raise an AttributeError

    lambda_schema = generate_recursive_schema_with_lambda()
    name_schema = generate_recursive_schema_with_name()
    assert lambda_schema == name_schema


def test_basic_dataclass():
    """
    Tests whether a dataclass (using @dataclass) can be transformed into a jsonschema
    using marshmallow-dataclass and JSONSchema.dump()
    """
    expected_data = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "definitions": {
            "TestDataClass": {
                "properties": {
                    "field_1": {"title": "field_1", "type": "integer"},
                    "field_2": {"title": "field_2", "type": "string"},
                    "field_3": {
                        "title": "field_3",
                        "type": "array",
                        "items": {"title": "field_3", "type": "string"},
                    },
                },
                "type": "object",
                "required": ["field_1", "field_2", "field_3"],
                "additionalProperties": False,
            }
        },
        "$ref": "#/definitions/TestDataClass",
    }
    json_schema = JSONSchema()

    @dataclass
    class TestDataClass:
        field_1: int
        field_2: str
        field_3: list[str]

    marshmallow_dataclass = class_schema(TestDataClass)()

    data = json_schema.dump(marshmallow_dataclass)
    assert data == expected_data


def test_union_dataclass():
    """
    Tests whether a dataclass with a variable with a union type (e.g. int | str)
    translates well through JSONSchema.dump()
    """
    expected_data = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "definitions": {
            "TestDataClass": {
                "properties": {
                    "field_1": {
                        "anyOf": [
                            {"title": "field_1", "type": "integer"},
                            {"title": "field_1", "type": "string"},
                        ]
                    }
                },
                "type": "object",
                "additionalProperties": False,
            }
        },
        "$ref": "#/definitions/TestDataClass",
    }
    json_schema = JSONSchema()

    @dataclass
    class TestDataClass:
        field_1: int | str | None

    marshmallow_dataclass = class_schema(TestDataClass)()
    data = json_schema.dump(marshmallow_dataclass)
    assert data == expected_data


def test_nested_dataclass():
    """
    Tests whether a dataclass with an internally defined dataclass translates well through JSONSchema.dump(), meaning
    both dataclasses should come out the other side.
    """

    @dataclass
    class SubDataClass:
        foo: int
        bar: list[int | str]

    @dataclass
    class TestDataClass:
        subclass: SubDataClass
        other: str

    marshmallow_dataclass = class_schema(TestDataClass)()
    data = JSONSchema().dump(marshmallow_dataclass)

    assert data["definitions"]["SubDataClass"]["type"] == "object"
    assert data["definitions"]["SubDataClass"]["properties"]["bar"]["items"] == {
        "anyOf": [{"title": "bar", "type": "integer"}, {"title": "bar", "type": "string"}]
    }
    assert data["definitions"]["SubDataClass"]["properties"]["foo"] == {"title": "foo", "type": "integer"}
    assert data["definitions"]["TestDataClass"]["type"] == "object"
    assert data["definitions"]["TestDataClass"]["properties"]["other"] == {"title": "other", "type": "string"}
    assert data["definitions"]["TestDataClass"]["properties"]["subclass"] == {
        "type": "object",
        "$ref": "#/definitions/SubDataClass",
    }
    assert data["definitions"]["TestDataClass"]["required"] == ["other", "subclass"]


def test_customfield_metadata_jsonschema_python_type():
    """
    NOTE: calculating additional metadata not currently in use
    Tests that specifying the equivalent pytpe in the metadata works for a custom field, and produces
    same result as using the deprecated _jsonschema_type_mapping function with equivalent json type.
    "jsonschema_python_type" should also be excluded from the dumped schema if set in metadata.
    """

    class CustomFieldPytype(fields.Field):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.metadata["jsonschema_python_type"] = str

    class CustomFieldPytype2(fields.Field):
        """This field tests setting pytpe on creation inside UserSchema"""

    class CustomFieldJSONSchemaType(fields.Field):
        def _jsonschema_type_mapping(self):
            return {"type": "string"}

    class UserSchema(Schema):
        custom_field_pytpe = CustomFieldPytype()
        custom_field_pytype2 = CustomFieldPytype2(metadata={"jsonschema_python_type": str})
        custom_field_jsonschema_type = CustomFieldJSONSchemaType()

    schema = UserSchema()
    dumped = validate_and_dump(schema)
    props = dumped["definitions"]["UserSchema"]["properties"]

    assert props["custom_field_pytpe"] == {"title": "custom_field_pytpe", "type": "string"}
    assert props["custom_field_pytype2"] == {"title": "custom_field_pytype2", "type": "string"}
    assert props["custom_field_jsonschema_type"] == {"type": "string"}


def test_customfield_metadata_pytype_mapping_overrides_jsonschema_type_mapping():
    """
    Test that if using pytpe mapping in metadata, that this overwrites the deprecated
    _jsonschema_type_mapping function if also provided.
    """

    class CustomField(fields.Field):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.metadata["jsonschema_python_type"] = str

        def _jsonschema_type_mapping(self):
            return {"type": "object"}

    class UserSchema(Schema):
        custom_field = CustomField()

    schema = UserSchema()
    dumped = validate_and_dump(schema)
    expected_schema = {"title": "custom_field", "type": "string"}
    assert dumped["definitions"]["UserSchema"]["properties"]["custom_field"] == expected_schema


def test_jsonschema_schema_passed_through():
    """
    NOTE: calculating additional metadata not currently in use
    Test for backwards compatibility, with changed behaviour of _jsonschema_type_mapping.
    If entire schema has been provided in _jsonschema_type_mapping, test that it still
    dumps as expected.
    """

    class CustomIntSchemaGiven(fields.Field):
        def _jsonschema_type_mapping(self):
            return {
                "type": "integer",
                "default": 7,
                "description": "Custom description",
                "title": "CustomInt",
            }

    class SchemaGiven(Schema):
        custom_field = CustomIntSchemaGiven(
            default=7,
            metadata={"description": "modified description", "title": "CustomInt"},
        )

    class CustomInt(fields.Field):
        def _jsonschema_type_mapping(self):
            return {"type": "integer", "description": "Custom description"}

    class SchemaInferred(Schema):
        custom_field = CustomInt(
            default=7,
            metadata={"description": "Custom description", "title": "CustomInt"},
        )

    class UserSchema(Schema):
        schema_given = fields.Nested(SchemaGiven())
        schema_inferred = fields.Nested(SchemaInferred())

    schema = UserSchema()
    dumped = validate_and_dump(schema)
    expected_schema = {
        "default": 7,
        "description": "Custom description",
        "title": "CustomInt",
        "type": "integer",
    }
    assert dumped["definitions"]["SchemaGiven"]["properties"]["custom_field"] == expected_schema
    del expected_schema["default"]  # inferred won't currently collect these extra bits of metadata
    del expected_schema["title"]
    assert dumped["definitions"]["SchemaInferred"]["properties"]["custom_field"] == expected_schema


def test_custom_list_inner_custom_field():
    """
    Test that custom lists, inner fields are captured correctly
    """

    class CustomFloat(fields.Field):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.metadata["jsonschema_python_type"] = float

    class NestedCustomList(fields.List):
        def __init__(self, **kwargs):
            super().__init__(CustomFloat(), **kwargs)

    class CustomList(fields.List):
        def __init__(self, **kwargs):
            super().__init__(fields.Float, **kwargs)

    class UserSchema(Schema):
        normal_list = fields.List(fields.Float, metadata={"title": "Float array"})
        normal_list_custom_inner = fields.List(CustomFloat, metadata={"title": "Float array"})
        custom_list = CustomList(metadata={"title": "Float array"})
        custom_list_custom_inner = NestedCustomList(metadata={"title": "Float array"})

    schema = UserSchema()
    dumped = validate_and_dump(schema)
    props = dumped["definitions"]["UserSchema"]["properties"]
    # The title in "items" should be only difference between each of the properties, remove for comparison
    for field_schema in props.values():
        field_schema["items"].pop("title", None)

    assert (
        props["normal_list"]
        == props["custom_list"]
        == props["normal_list_custom_inner"]
        == props["custom_list_custom_inner"]
    )


def test_custom_dict_custom_values():
    """
    Test that custom dicts, keys and values are captured correctly
    """

    class CustomKey(fields.Field):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.metadata["jsonschema_python_type"] = str

    class CustomValue(fields.Field):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.metadata["jsonschema_python_type"] = int

    class CustomDict(fields.Dict):
        def __init__(self, keys, values, **kwargs):
            super().__init__(keys=keys, values=values, **kwargs)

    class UserSchema(Schema):
        normal_dict = fields.Dict(keys=fields.String, values=fields.Integer, metadata={"title": "dict field"})
        normal_dict_custom_values = fields.Dict(
            keys=fields.String, values=CustomValue(), metadata={"title": "dict field"}
        )
        normal_dict_custom_keys = fields.Dict(keys=CustomKey(), values=fields.Integer, metadata={"title": "dict field"})
        normal_dict_custom_items = fields.Dict(keys=CustomKey(), values=CustomValue(), metadata={"title": "dict field"})
        custom_dict = CustomDict(keys=fields.String, values=fields.Integer, metadata={"title": "dict field"})
        custom_dict_custom_values = CustomDict(
            keys=fields.String, values=CustomValue(), metadata={"title": "dict field"}
        )
        custom_dict_custom_keys = CustomDict(keys=CustomKey(), values=fields.Integer, metadata={"title": "dict field"})
        custom_dict_custom_items = CustomDict(keys=CustomKey(), values=CustomValue(), metadata={"title": "dict field"})

    schema = UserSchema()
    dumped = validate_and_dump(schema)
    props = dumped["definitions"]["UserSchema"]["properties"]
    props_list = []
    # The title in "additionalProperties" should be only diff between each of the properties, remove for comparison
    for field_schema in props.values():
        field_schema["additionalProperties"].pop("title", None)
        props_list.append(field_schema)

    assert all(d == props_list[0] for d in props_list)


@pytest.mark.skip("This functionality is not currently in use to retain backwards compatibility")
def test_custom_jsonschema_python_type_list_items_exists():
    """
    When a custom fields.Field instance is used with jsonschema_python_type=list or _jsonschema_type_mapping "array",
    an empty "items" schema should be present.
    If an 'inner' attribute is present in a custom list-like field, then this should be used.
    """

    # Custom fields which we want to treat like lists: No inner attribute defined
    class CustomListField(fields.Field):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.metadata["jsonschema_python_type"] = list

    class JsonSchemaTypeField(fields.Field):
        def _jsonschema_type_mapping(self):
            return {"type": "array"}

    # Custom fields which we want to treat like lists: Inner attribute defined
    class CustomListFieldWithInner(fields.Field):
        def __init__(self, inner_field: fields.Field, **kwargs):
            super().__init__(**kwargs)
            self.metadata["jsonschema_python_type"] = list
            self.inner = inner_field

    class JsonSchemaTypeFieldWithInner(fields.Field):
        def __init__(self, inner_field: fields.Field, **kwargs):
            super().__init__(**kwargs)
            self.inner = inner_field

        def _jsonschema_type_mapping(self):
            return {"type": "array"}

    class UserSchema(Schema):
        custom_field = CustomListField()
        jsonschema_field = JsonSchemaTypeField()
        custom_field_inner = CustomListFieldWithInner(inner_field=fields.String())
        jsonschema_field_inner = JsonSchemaTypeFieldWithInner(inner_field=fields.String())

    schema = UserSchema()
    dumped = validate_and_dump(schema)
    pytype_prop = dumped["definitions"]["UserSchema"]["properties"]["custom_field"]
    jsonschema_prop = dumped["definitions"]["UserSchema"]["properties"]["jsonschema_field"]
    pytype_inner_prop = dumped["definitions"]["UserSchema"]["properties"]["custom_field_inner"]
    jsonschema_inner_prop = dumped["definitions"]["UserSchema"]["properties"]["jsonschema_field_inner"]
    for nested_json in (pytype_prop, jsonschema_prop):
        assert nested_json["type"] == "array"
        assert "items" in nested_json
        assert nested_json["items"] == {}
    for nested_json in (pytype_inner_prop, jsonschema_inner_prop):
        assert nested_json["type"] == "array"
        assert "items" in nested_json
        assert nested_json["items"] == {"title": "", "type": "string"}


@pytest.mark.skip("This functionality is not currently in use to retain backwards compatibility")
def test_custom_jsonschema_python_type_dict_additional_properties_exists():
    """
    When a custom fields.Field instance is used with jsonschema_python_type=dict or _jsonschema_type_mapping "object",
    an empty "additionalProperties" schema should be present
    """

    # Custom fields which we want to treat like dicts: No value_field attribute defined
    class CustomDictField(fields.Field):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.metadata["jsonschema_python_type"] = dict

    class JsonSchemaTypeField(fields.Field):
        def _jsonschema_type_mapping(self):
            return {"type": "object"}

    # Custom fields which we want to treat like dicts: value_field attribute defined
    class CustomDictFieldWithValueField(fields.Field):
        def __init__(self, value_field: fields.Field, **kwargs):
            super().__init__(**kwargs)
            self.metadata["jsonschema_python_type"] = dict
            self.value_field = value_field

    class JsonSchemaTypeFieldWithValueField(fields.Field):
        def __init__(self, value_field: fields.Field, **kwargs):
            super().__init__(**kwargs)
            self.value_field = value_field

        def _jsonschema_type_mapping(self):
            return {"type": "object"}

    class UserSchema(Schema):
        custom_field = CustomDictField()
        jsonschema_field = JsonSchemaTypeField()
        custom_field_value = CustomDictFieldWithValueField(value_field=fields.String())
        jsonschema_field_value = JsonSchemaTypeFieldWithValueField(value_field=fields.String())

    schema = UserSchema()
    dumped = validate_and_dump(schema)
    pytype_prop = dumped["definitions"]["UserSchema"]["properties"]["custom_field"]
    jsonschema_prop = dumped["definitions"]["UserSchema"]["properties"]["jsonschema_field"]
    pytype_value_prop = dumped["definitions"]["UserSchema"]["properties"]["custom_field_value"]
    jsonschema_value_prop = dumped["definitions"]["UserSchema"]["properties"]["jsonschema_field_value"]
    for nested_json in (pytype_prop, jsonschema_prop):
        assert nested_json["type"] == "object"
        assert "additionalProperties" in nested_json
        assert nested_json["additionalProperties"] == {}
    for nested_json in (pytype_value_prop, jsonschema_value_prop):
        assert nested_json["type"] == "object"
        assert "additionalProperties" in nested_json
        assert nested_json["additionalProperties"] == {"title": "", "type": "string"}


@pytest.mark.skip("This functionality is not currently in use to retain backwards compatibility")
def test_can_have_custom_field_schema_without_type():
    class JsonSchemaEvilField(fields.Field):
        def _jsonschema_type_mapping(self):
            return {"evil_field": "true"}

    class UserSchema(Schema):
        custom_field = JsonSchemaEvilField()

    schema = UserSchema()
    dumped = validate_and_dump(schema)
    assert dumped["definitions"]["UserSchema"]["properties"]["custom_field"] == {
        "evil_field": "true",
        "title": "custom_field",
    }
