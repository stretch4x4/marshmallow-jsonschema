import builtins
import datetime
import decimal
import typing
import uuid
import warnings
from enum import Enum
from inspect import isclass

from marshmallow import EXCLUDE, INCLUDE, RAISE, Schema, fields, missing, validate

# marshmallow.fields.Enum support has been added in marshmallow v3.18
# see https://github.com/marshmallow-code/marshmallow/blob/dev/CHANGELOG.rst#3180-2022-09-15
from marshmallow import __version__ as _marshmallow_version
from marshmallow.class_registry import get_class
from marshmallow.decorators import post_dump
from marshmallow.utils import _Missing

# the package "packaging" is a requirement of marshmallow itself => we don't need to install it separately
# see https://github.com/marshmallow-code/marshmallow/blob/ddbe06f923befe754e213e03fb95be54e996403d/setup.py#L61
from packaging.version import Version

from .exceptions import UnsupportedValueError
from .validation import (
    handle_any_of,
    handle_equal,
    handle_length,
    handle_one_of,
    handle_range,
    handle_regexp,
)


def marshmallow_version_supports_native_enums() -> bool:
    """
    returns true if and only if the version of marshmallow installed supports enums natively
    """
    return Version(_marshmallow_version) >= Version("3.18")


try:
    from marshmallow_enum import EnumField as MarshmallowEnumEnumField
    from marshmallow_enum import LoadDumpOptions

    ALLOW_MARSHMALLOW_ENUM_ENUMS = True
except ImportError:
    ALLOW_MARSHMALLOW_ENUM_ENUMS = False

ALLOW_MARSHMALLOW_NATIVE_ENUMS = marshmallow_version_supports_native_enums()
if ALLOW_MARSHMALLOW_NATIVE_ENUMS:
    from marshmallow.fields import Enum as MarshmallowNativeEnumField

__all__ = ("JSONSchema",)

PY_TO_JSON_TYPES_MAP = {
    dict: {"type": "object"},
    list: {"type": "array"},
    datetime.time: {"type": "string", "format": "time"},
    datetime.timedelta: {
        # TODO explore using 'range'?
        "type": "string"
    },
    datetime.datetime: {"type": "string", "format": "date-time"},
    datetime.date: {"type": "string", "format": "date"},
    uuid.UUID: {"type": "string", "format": "uuid"},
    str: {"type": "string"},
    bytes: {"type": "string"},
    decimal.Decimal: {"type": "number", "format": "decimal"},
    set: {"type": "array"},
    tuple: {"type": "array"},
    float: {"type": "number", "format": "float"},
    int: {"type": "integer"},
    bool: {"type": "boolean"},
    Enum: {"type": "string"},
}

# We use these pairs to get proper python type from marshmallow type.
# We can't use mapping as earlier Python versions might shuffle dict contents
# and then `fields.Number` might end up before `fields.Integer`.
# As we perform sequential subclass check to determine proper Python type,
# we can't let that happen.
MARSHMALLOW_TO_PY_TYPES_PAIRS = [
    # This part of a mapping is carefully selected from marshmallow source code,
    # see marshmallow.BaseSchema.TYPE_MAPPING.
    (fields.UUID, uuid.UUID),
    (fields.String, str),
    (fields.Float, float),
    (fields.Raw, str),
    (fields.Boolean, bool),
    (fields.Integer, int),
    (fields.Time, datetime.time),
    (fields.Date, datetime.date),
    (fields.TimeDelta, datetime.timedelta),
    (fields.DateTime, datetime.datetime),
    (fields.Decimal, decimal.Decimal),
    # These are some mappings that generally make sense for the rest
    # of marshmallow fields.
    (fields.Email, str),
    (fields.Dict, dict),
    (fields.Url, str),
    (fields.List, list),
    (fields.Tuple, tuple),
    (fields.Number, decimal.Decimal),
    (fields.IP, str),
    (fields.IPInterface, str),
    # This one is here just for completeness sake and to check for
    # unknown marshmallow fields more cleanly.
    (fields.Nested, dict),
]

if ALLOW_MARSHMALLOW_NATIVE_ENUMS:
    MARSHMALLOW_TO_PY_TYPES_PAIRS.append((MarshmallowNativeEnumField, Enum))
if ALLOW_MARSHMALLOW_ENUM_ENUMS:
    # We currently only support loading enum's from their names. So the possible
    # values will always map to string in the JSONSchema
    MARSHMALLOW_TO_PY_TYPES_PAIRS.append((MarshmallowEnumEnumField, Enum))


FIELD_VALIDATORS = {
    validate.Equal: handle_equal,
    validate.Length: handle_length,
    validate.OneOf: handle_one_of,
    validate.ContainsOnly: handle_any_of,
    validate.Range: handle_range,
    validate.Regexp: handle_regexp,
}

# Metadata item to specify what python type to interpret custom field classes as
PYTYPE_KEY = "jsonschema_python_type"


def _resolve_additional_properties(cls) -> bool:
    meta = cls.Meta

    additional_properties = getattr(meta, "additional_properties", None)
    if additional_properties is not None:
        if additional_properties in (True, False):
            return additional_properties
        msg = "`additional_properties` must be either True or False"
        raise UnsupportedValueError(msg)

    unknown = getattr(meta, "unknown", None)
    if unknown is None:
        return False
    if unknown in (RAISE, EXCLUDE):
        return False
    if unknown == INCLUDE:
        return True
    # This is probably unreachable as of marshmallow 3.16.0
    msg = f"Unknown value {unknown!s} for `unknown`"
    raise UnsupportedValueError(msg)


class JSONSchema(Schema):
    """Converts to JSONSchema as defined by http://json-schema.org/."""

    properties = fields.Method("get_properties")
    type = fields.Constant("object")
    required = fields.Method("get_required")

    def __init__(self, *args, **kwargs) -> None:
        """Setup internal cache of nested fields, to prevent recursion.

        :param bool props_ordered: if `True` order of properties will be save as declare in class,
                                   else will using sorting, default is `False`.
                                   Note: For the marshmallow scheme, also need to enable
                                   ordering of fields too (via `class Meta`, attribute `ordered`).
        """
        self._nested_schema_classes: dict[str, dict[str, typing.Any]] = {}
        self.nested = kwargs.pop("nested", False)
        self.props_ordered = kwargs.pop("props_ordered", False)
        self.opts.ordered = self.props_ordered
        super().__init__(*args, **kwargs)

    def get_properties(self, obj) -> dict[str, dict[str, typing.Any]]:
        """Fill out properties field."""
        properties = self.dict_class()

        if self.props_ordered:
            fields_items_sequence = obj.fields.items()
        elif callable(obj):
            fields_items_sequence = sorted(obj().fields.items())
        else:
            fields_items_sequence = sorted(obj.fields.items())

        for _field_name, field in fields_items_sequence:
            schema = self._get_schema_for_field(obj, field)
            properties[field.metadata.get("name") or field.data_key or field.name] = schema

        return properties

    def get_required(self, obj) -> list[str] | _Missing:
        """Fill out required field."""
        required = []
        field_items_iterable = sorted(obj().fields.items()) if callable(obj) else sorted(obj.fields.items())
        for _field_name, field in field_items_iterable:
            if field.required:
                required.append(field.data_key or field.name)

        return required or missing

    def _from_python_type(self, obj, field, pytype: builtins.type) -> dict[str, typing.Any]:
        """Get schema definition from python type."""
        json_schema = {"title": field.attribute or field.name or ""}

        json_schema.update(dict(PY_TO_JSON_TYPES_MAP[pytype]))

        if field.dump_only:
            json_schema["readOnly"] = True

        if field.default is not missing and not callable(field.default):
            json_schema["default"] = field.default

        if ALLOW_MARSHMALLOW_NATIVE_ENUMS and isinstance(field, MarshmallowNativeEnumField):
            json_schema["enum"] = self._get_marshmallow_native_enum_values(field)
        elif ALLOW_MARSHMALLOW_ENUM_ENUMS and isinstance(field, MarshmallowEnumEnumField):
            json_schema["enum"] = self._get_marshmallow_enum_enum_values(field)

        if field.allow_none:
            previous_type = json_schema["type"]
            json_schema["type"] = [previous_type, "null"]

        # NOTE: doubled up to maintain backwards compatibility
        metadata = field.metadata.get("metadata", {})
        metadata.update(field.metadata)

        for md_key, md_val in metadata.items():
            if md_key in ("metadata", "name", PYTYPE_KEY):
                continue
            json_schema[md_key] = md_val

        if pytype in (list, set, tuple):
            if isinstance(field, fields.List) or hasattr(field, "inner"):
                json_schema["items"] = self._get_schema_for_field(obj, field.inner)
            elif isinstance(field, fields.Tuple):
                msg = (
                    "Conversion for fields of type 'fields.Tuple' are not currently supported, 'items' will be empty"
                    f" in the schema for '{json_schema['title']}'."
                )
                warnings.warn(msg, UserWarning, stacklevel=2)
                json_schema["items"] = {}
            else:
                msg = (
                    f"Cannot determine inner field for custom '{json_schema['title']}' array field, 'items' will be"
                    " empty in the schema. Consider subclassing 'fields.List', or defining an appropriate "
                    "'self.inner' attribute for this custom field."
                )
                warnings.warn(msg, UserWarning, stacklevel=2)
                json_schema["items"] = {}

        if pytype is dict:
            if hasattr(field, "value_field") and field.value_field is not None:
                json_schema["additionalProperties"] = self._get_schema_for_field(obj, field.value_field)
            else:
                msg = (
                    f"Cannot determine value field for custom '{json_schema['title']}' dict field, "
                    "'additionalProperties' will be empty in the schema. Consider subclassing 'fields.Dict', or "
                    "defining an appropriate 'self.value_field' attribute for this custom field."
                )
                warnings.warn(msg, UserWarning, stacklevel=2)
                json_schema["additionalProperties"] = {}
        return json_schema

    def _from_custom_field_type(
        self, obj, field: fields.Field, type_mapping: dict[str, typing.Any]
    ) -> dict[str, typing.Any]:
        """(DEPRECATED) Get schema definition for a custom field."""
        msg = (
            "Use of the '_jsonschema_type_mapping' method is deprecated. For custom field support, consider "
            "specifying the equivalent python type instead, using the 'jsonschema_python_type' key in metadata."
        )
        warnings.warn(msg, DeprecationWarning, stacklevel=2)
        json_schema = type_mapping

        json_schema["title"] = field.attribute or field.name or ""

        if field.dump_only:
            json_schema["readOnly"] = True

        if field.default is not missing and not callable(field.default):
            json_schema["default"] = field.default

        if ALLOW_MARSHMALLOW_NATIVE_ENUMS and isinstance(field, MarshmallowNativeEnumField):
            json_schema["enum"] = self._get_marshmallow_native_enum_values(field)
        elif ALLOW_MARSHMALLOW_ENUM_ENUMS and isinstance(field, MarshmallowEnumEnumField):
            json_schema["enum"] = self._get_marshmallow_enum_enum_values(field)

        if field.allow_none:
            previous_type = json_schema["type"]
            json_schema["type"] = [previous_type, "null"]

        # NOTE: doubled up to maintain backwards compatibility
        metadata = field.metadata.get("metadata", {})
        metadata.update(field.metadata)

        for md_key, md_val in metadata.items():
            if md_key in ("metadata", "name", PYTYPE_KEY):
                continue
            json_schema[md_key] = md_val

        if "array" in json_schema["type"]:
            if isinstance(field, fields.List) or hasattr(field, "inner"):
                json_schema["items"] = self._get_schema_for_field(obj, field.inner)
            else:
                msg = (
                    f"Cannot determine inner field for custom '{json_schema['title']}' array field, 'items' will be"
                    " empty in the schema. Consider subclassing 'fields.List', or defining an appropriate "
                    "'self.inner' attribute for this custom field."
                )
                warnings.warn(msg, UserWarning, stacklevel=2)
                json_schema["items"] = {}

        if "object" in json_schema["type"]:
            if hasattr(field, "value_field"):
                json_schema["additionalProperties"] = self._get_schema_for_field(obj, field.value_field)
            else:
                msg = (
                    f"Cannot determine value field for custom '{json_schema['title']}' dict field, "
                    "'additionalProperties' will be empty in the schema. Consider subclassing 'fields.Dict', or "
                    "defining an appropriate 'self.value_field' attribute for this custom field."
                )
                warnings.warn(msg, UserWarning, stacklevel=2)
                json_schema["additionalProperties"] = {}
        return json_schema

    def _get_marshmallow_enum_enum_values(self, field) -> list[str]:
        if not ALLOW_MARSHMALLOW_ENUM_ENUMS and not isinstance(field, MarshmallowEnumEnumField):
            msg = "Expected a MarshmallowEnumEnumField with enum enums enabled"
            raise TypeError(msg)

        if field.load_by == LoadDumpOptions.value:
            # Python allows enum values to be almost anything, so it's easier to just load from the
            # names of the enum's which will have to be strings.
            msg = "Currently do not support JSON schema for enums loaded by value"
            raise NotImplementedError(msg)

        return [value.name for value in field.enum]

    def _get_marshmallow_native_enum_values(self, field) -> list[str]:
        """
        Extract the names of enum members from a Marshmallow native EnumField.
        Only supports fields configured with ``by_name``
        """

        if not ALLOW_MARSHMALLOW_NATIVE_ENUMS and not isinstance(field, MarshmallowNativeEnumField):
            msg = "Expected a MarshmallowNativeEnumField with native enums enabled"
            raise TypeError(msg)

        if field.by_value:
            # Python allows enum values to be almost anything, so it's easier to just load from the
            # names of the enum's which will have to be strings.
            msg = "Currently do not support JSON schema for enums loaded by value"
            raise NotImplementedError(msg)

        return [value.name for value in field.enum]

    def _from_union_schema(self, obj, field) -> dict[str, list[typing.Any]]:
        """
        Get a union type schema. Uses anyOf to allow the value to be any of the provided sub fields.
        Currently there are two implementations of union fields, one in marshmallow_dataclass
        and one in marshmallow_union. To avoid excessive imports, this function just tries to access
        the relevant attribute instead of type checking for Union.
        """
        # If obj has union_fields attribute, probably a marshmallow_dataclass type of Union.
        # Does some type checking on union_fields to ensure it will not fail due to an access issue.
        if (
            hasattr(field, "union_fields")
            and isinstance(field.union_fields, list)
            and all(isinstance(field_pair, tuple) for field_pair in field.union_fields)
        ):
            return {"anyOf": [self._get_schema_for_field(obj, sub_field) for _, sub_field in field.union_fields]}

        # If obj has _candidate_fields attribute, probably a marshmallow_union type of Union.
        if hasattr(field, "_candidate_fields") and isinstance(field._candidate_fields, list):
            return {"anyOf": [self._get_schema_for_field(obj, sub_field) for sub_field in field._candidate_fields]}

        # If neither of these attributes exists, it is not an implemented union type.
        msg = f"Field {field} is not a supported Union type."
        raise TypeError(msg)

    def _get_python_type(self, field: fields.Field) -> builtins.type:
        """Get python type based on field subclass"""
        if PYTYPE_KEY in field.metadata:
            pytype = field.metadata[PYTYPE_KEY]
            if not isinstance(pytype, type):
                msg = (
                    "A python type was not supplied for 'jsonschema_python_type', in "
                    f"'{field.attribute or field.name or field.__class__.__name__}'"
                )
                raise TypeError(msg)
            if pytype not in PY_TO_JSON_TYPES_MAP:
                msg = (
                    f"'{PYTYPE_KEY}' is not a supported python type for dumping in marshmallow_jsonschema. In field "
                    "'{field.attribute or field.name or field.__class__.__name__}'"
                )
                raise UnsupportedValueError(msg)
            return pytype

        for map_class, pytype in MARSHMALLOW_TO_PY_TYPES_PAIRS:
            if issubclass(field.__class__, map_class):
                return pytype

        msg = f"unsupported field type {field!s}"
        raise UnsupportedValueError(msg)

    def _get_value_from_obj_or_metadata(self, field: fields.Field, attr: str) -> None | typing.Any:
        """
        Helper function to search for and return an attribute. First checks for a direct attribute, then checks in
        metadata. If the attribute value is a function, run and return the function output.
        Returns None if the attribute is not found in either location.
        """
        if hasattr(field, attr):
            value = getattr(field, attr)
            return value() if callable(value) else value
        if attr in field.metadata:
            value = field.metadata[attr]
            return value() if callable(value) else value
        return None

    def _get_schema_for_field(self, obj, field):
        """Get schema and validators for field."""
        # For backwards compatibility, can still use '_jsonschema_type_mapping' with JSON equivalent Field type.
        # Will just use the 'jsonschema_python_type' metadata mapping if present
        type_mapping = self._get_value_from_obj_or_metadata(field, "_jsonschema_type_mapping")
        if type_mapping is not None and PYTYPE_KEY not in field.metadata:
            schema = self._from_custom_field_type(obj, field, type_mapping)
        elif isinstance(field, fields.Nested):
            # Special treatment for nested fields.
            schema = self._from_nested_schema(obj, field)
        elif hasattr(field, "union_fields") or hasattr(field, "_candidate_fields"):
            schema = self._from_union_schema(obj, field)
        else:
            pytype = self._get_python_type(field)
            schema = self._from_python_type(obj, field, pytype)
        # Apply any and all validators that field may have
        for validator in field.validators:
            if validator.__class__ in FIELD_VALIDATORS:
                schema = FIELD_VALIDATORS[validator.__class__](schema, field, validator, obj)
            else:
                base_class = getattr(validator, "_jsonschema_base_validator_class", None)
                if base_class is not None and base_class in FIELD_VALIDATORS:
                    schema = FIELD_VALIDATORS[base_class](schema, field, validator, obj)
        return schema

    def _from_nested_schema(self, obj, field):
        """Support nested field."""
        nested = get_class(field.nested) if isinstance(field.nested, (str, bytes)) else field.nested

        if isclass(nested) and issubclass(nested, Schema):
            name = nested.__name__
            only = field.only
            exclude = field.exclude
            nested_cls = nested
            nested_instance = nested(only=only, exclude=exclude, context=obj.context)
        elif callable(nested):
            nested_instance = nested()
            nested_type = type(nested_instance)
            name = nested_type.__name__
            nested_cls = nested_type.__class__
        else:
            nested_cls = nested.__class__
            name = nested_cls.__name__
            nested_instance = nested

        outer_name = obj.__class__.__name__
        # If this is not a schema we've seen, and it's not this schema (checking this for recursive schemas),
        # put it in our list of schema defs
        if name not in self._nested_schema_classes and name != outer_name:
            wrapped_nested = self.__class__(nested=True)
            wrapped_dumped = wrapped_nested.dump(nested_instance)

            wrapped_dumped["additionalProperties"] = _resolve_additional_properties(nested_cls)

            self._nested_schema_classes[name] = wrapped_dumped

            self._nested_schema_classes.update(wrapped_nested._nested_schema_classes)

        # and the schema is just a reference to the def
        schema = self._schema_base(name)

        # NOTE: doubled up to maintain backwards compatibility
        metadata = field.metadata.get("metadata", {})
        metadata.update(field.metadata)

        for md_key, md_val in metadata.items():
            if md_key in ("metadata", "name"):
                continue
            schema[md_key] = md_val

        if field.default is not missing and not callable(field.default):
            schema["default"] = nested_instance.dump(field.default)

        if field.many:
            schema = {
                "type": "array" if field.required else ["array", "null"],
                "items": schema,
            }

        return schema

    def _schema_base(self, name):
        return {"type": "object", "$ref": f"#/definitions/{name}"}

    def dump(self, obj, **kwargs):
        """Take obj for later use: using class name to namespace definition."""
        self.obj = obj
        return super().dump(obj, **kwargs)

    @post_dump
    def wrap(self, data, **_) -> dict[str, typing.Any]:
        """Wrap this with the root schema definitions."""
        if self.nested:  # no need to wrap, will be in outer defs
            return data

        cls = self.obj.__class__
        name = cls.__name__

        data["additionalProperties"] = _resolve_additional_properties(cls)

        self._nested_schema_classes[name] = data
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "definitions": self._nested_schema_classes,
            "$ref": f"#/definitions/{name}",
        }
