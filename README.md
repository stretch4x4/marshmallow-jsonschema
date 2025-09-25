# marshmallow-jsonschema

> **NOTE**
>
> This is a maintained refactor of the original [marshmallow-jsonschema project](https://github.com/fuhrysteve/marshmallow-jsonschema).
>
> The main goals of this refactor were:
>
> - Fix some long standing bugs
> - Support newer versions of Python
> - Publish a more recent release
> - Modernise builds and tooling to enable active development and future work

## Overview

<!--- TODO: re-enable the following badge once we split coverage and testing - put after testing --->
<!--- ![Coverage]&#40;https://github.com/stretch4x4/marshmallow-jsonschema/actions/workflows/pytest_and_coverage.yml/badge.svg&#41;) --->
![Build Status](https://github.com/stretch4x4/marshmallow-jsonschema/actions/workflows/pytest_and_coverage.yml/badge.svg)
[![CodeQL](https://github.com/stretch4x4/marshmallow-jsonschema/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/stretch4x4/marshmallow-jsonschema/actions/workflows/codeql-analysis.yml)
[![OSSAR](https://github.com/stretch4x4/marshmallow-jsonschema/actions/workflows/ossar-analysis.yml/badge.svg)](https://github.com/stretch4x4/marshmallow-jsonschema/actions/workflows/ossar-analysis.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
![PyPI - Version](https://img.shields.io/pypi/v/marshmallow-jsonschema)
![GitHub Release](https://img.shields.io/github/v/release/stretch4x4/marshmallow-jsonschema)


 marshmallow-jsonschema translates marshmallow schemas into
 JSON Schema Draft v7 compliant jsonschema. See http://json-schema.org/

### Why would I want my schema translated to JSON?

What are the use cases for this? Let's say you have a
marshmallow schema in python, but you want to render your
schema as a form in another system (for example: a web browser
or mobile device).

## Installation

Requires python>=3.10 and marshmallow>=3.11. (For python 2 & marshmallow 2 support, please use
marshmallow-jsonschema<0.11)

```
pip install marshmallow-jsonschema
```

## Some Client tools can render forms using JSON Schema

* [react-jsonschema-form](https://github.com/mozilla-services/react-jsonschema-form) (recommended)
  * See below extension for this excellent library!
* https://github.com/brutusin/json-forms
* https://github.com/jdorn/json-editor
* https://github.com/ulion/jsonform

## Examples

### Simple Example

```python
from marshmallow import Schema, fields
from marshmallow_jsonschema import JSONSchema

class UserSchema(Schema):
    username = fields.String()
    age = fields.Integer()
    birthday = fields.Date()

user_schema = UserSchema()

json_schema = JSONSchema()
json_schema.dump(user_schema)
```

Yields:

```python
{'properties': {'age': {'format': 'integer',
                        'title': 'age',
                        'type': 'number'},
                'birthday': {'format': 'date',
                             'title': 'birthday',
                             'type': 'string'},
                'username': {'title': 'username', 'type': 'string'}},
 'required': [],
 'type': 'object'}
```

### Nested Example

```python
from marshmallow import Schema, fields
from marshmallow_jsonschema import JSONSchema
from tests import UserSchema


class Athlete(object):
    user_schema = UserSchema()

    def __init__(self):
        self.name = 'sam'


class AthleteSchema(Schema):
    user_schema = fields.Nested(JSONSchema)
    name = fields.String()


athlete = Athlete()
athlete_schema = AthleteSchema()

athlete_schema.dump(athlete)
```

### Complete example Flask application using brutisin/json-forms

![Screenshot](http://i.imgur.com/jJv1wFk.png)

This example renders a form not dissimilar to how [wtforms](https://github.com/wtforms/wtforms) might render a form.

However rather than rendering the form in python, the JSON Schema is rendered using the
javascript library [brutusin/json-forms](https://github.com/brutusin/json-forms).


```python
from flask import Flask, jsonify
from marshmallow import Schema, fields
from marshmallow_jsonschema import JSONSchema

app = Flask(__name__)


class UserSchema(Schema):
    name = fields.String()
    address = fields.String()


@app.route('/schema')
def schema():
    schema = UserSchema()
    return jsonify(JSONSchema().dump(schema))


@app.route('/')
def home():
    return '''<!DOCTYPE html>
<head>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/brutusin.json-forms/1.3.0/css/brutusin-json-forms.css"><Paste>
<script src="https://code.jquery.com/jquery-1.12.1.min.js" integrity="sha256-I1nTg78tSrZev3kjvfdM5A5Ak/blglGzlaZANLPDl3I=" crossorigin="anonymous"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/underscore.string/3.3.4/underscore.string.min.js"></script>
<script src="https://cdn.jsdelivr.net/brutusin.json-forms/1.3.0/js/brutusin-json-forms.min.js"></script>
<script>
$(document).ready(function() {
    $.ajax({
        url: '/schema'
        , success: function(data) {
            var container = document.getElementById('myform');
            var BrutusinForms = brutusin["json-forms"];
            var bf = BrutusinForms.create(data);
            bf.render(container);
        }
    });
});
</script>
</head>
<body>
<div id="myform"></div>
</body>
</html>
'''


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)

```


## Advanced usage
### Custom Type support

For custom field classes, you can add a mapping to an equivalent python type using the `'jsonschema_python_type'` key inside `metadata`.

If requiring proper schema validation and nesting with custom list-like fields, consider subclassing `fields.List`, or alternatively provide a `self.inner` attribute, set to a field instance representing the type of the items inside the custom list.

Example custom field definitions, using `'jsonschema_python_type'`:

```python
class Colour(fields.Field):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.metadata["jsonschema_python_type"] = str

    def _serialize(self, value, _attr, _obj):
        r, g, b = value
        return f"#{r:x}{g:x}{b:x}"

class ColourList(fields.Field):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.metadata["jsonschema_python_type"] = list
        self.inner = Colour()

class FlexibleType(fields.Field):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print(f"This is field treated like a {self.metadata['jsonschema_python_type']}")

class UserSchema(Schema):
        favourite_colour = Colour()
        close_favourites = ColourList()
        bool_field = FlexibleType(metadata=("jsonschema_python_type": bool))
        int_field = FlexibleType(metadata=("jsonschema_python_type": int))

schema = UserSchema()
json_schema = JSONSchema()
json_schema.dump(schema)
```


### [__deprecated__] Custom Type support using `_jsonschema_type_mapping()`

> `_jsonschema_type_mapping()` is deprecated in favour of using `'jsonschema_python_type'` for type aliases, as described above.

Simply add a `_jsonschema_type_mapping` method to your field
so we know how it ought to get serialized to JSON Schema.

A common use case for this is creating a dropdown menu using
enum (see Gender below).


```python
class Colour(fields.Field):

    def _jsonschema_type_mapping(self):
        return {
            'type': 'string',
        }

    def _serialize(self, value, _attr, _obj):
        r, g, b = value
        return f"#{r:x}{g:x}{b:x}"

class Gender(fields.String):
    def _jsonschema_type_mapping(self):
        return {
            'type': 'string',
            'enum': ['Male', 'Female']
        }


class UserSchema(Schema):
    name = fields.String(required=True)
    favourite_colour = Colour()
    gender = Gender()

schema = UserSchema()
json_schema = JSONSchema()
json_schema.dump(schema)
```


### React-JSONSchema-Form Extension

[react-jsonschema-form](https://react-jsonschema-form.readthedocs.io/en/latest/)
is a library for rendering jsonschemas as a form using React. It is very powerful
and full featured.. the catch is that it requires a proprietary
[`uiSchema`](https://react-jsonschema-form.readthedocs.io/en/latest/form-customization/#the-uischema-object)
to provide advanced control how the form is rendered.
[Here's a live playground](https://rjsf-team.github.io/react-jsonschema-form/)

*(new in version 0.10.0)*

```python
from marshmallow_jsonschema.extensions import ReactJsonSchemaFormJSONSchema

class MySchema(Schema):
    first_name = fields.String(
        metadata={
            'ui:autofocus': True,
        }
    )
    last_name = fields.String()

    class Meta:
        react_uischema_extra = {
            'ui:order': [
                'first_name',
                'last_name',
            ]
        }


json_schema_obj = ReactJsonSchemaFormJSONSchema()
schema = MySchema()

# here's your jsonschema
data = json_schema_obj.dump(schema)

# ..and here's your uiSchema!
ui_schema_json = json_schema_obj.dump_uischema(schema)
```
