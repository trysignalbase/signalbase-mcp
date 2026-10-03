"""JSON-Schema subset validator shared by the contract-driven v3 profiles.

Lifted verbatim out of recruiting_v3 when monitoring became a second profile.
Both profiles validate a connector's arguments against the generated contract
before any network call, so a malformed agent argument never reaches the API.
"""

import re


def validate(value, schema, root=None, path="arguments"):
    root = root or schema
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        return validate(value, target, root, path)
    if "anyOf" in schema:
        for child in schema["anyOf"]:
            try:
                validate(value, child, root, path)
                return
            except ValueError:
                pass
        raise ValueError(f"{path}: no allowed argument shape matched")
    kind = schema.get("type")
    valid = {"object": isinstance(value, dict), "array": isinstance(value, list),
             "string": isinstance(value, str), "boolean": isinstance(value, bool),
             "integer": isinstance(value, int) and not isinstance(value, bool),
             "number": isinstance(value, (int, float)) and not isinstance(value, bool),
             "null": value is None}
    if kind and not valid.get(kind, False):
        raise ValueError(f"{path}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: use one of {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{path}: expected {schema['const']}")
    if kind == "object":
        properties = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(value)
        extra = set(value) - set(properties)
        if missing:
            raise ValueError(f"{path}: missing {', '.join(sorted(missing))}")
        if extra and schema.get("additionalProperties") is False:
            raise ValueError(f"{path}: unknown fields {', '.join(sorted(extra))}")
        for key, item in value.items():
            if key in properties:
                validate(item, properties[key], root, f"{path}.{key}")
    if kind == "array":
        low, high = schema.get("minItems", 0), schema.get("maxItems", 100000)
        if len(value) < low or len(value) > high:
            bound = f"at least {low}" if len(value) < low else f"at most {high}"
            raise ValueError(
                f"{path}: {len(value)} items given; this field accepts {bound}"
                + (". Split the list across several calls" if len(value) > high else "")
            )
        for index, item in enumerate(value):
            validate(item, schema.get("items", {}), root, f"{path}[{index}]")
    if kind == "string":
        low, high = schema.get("minLength", 0), schema.get("maxLength", 1000000)
        if len(value) < low or len(value) > high:
            bound = f"at least {low}" if len(value) < low else f"at most {high}"
            raise ValueError(f"{path}: {len(value)} characters given; this field accepts {bound}")
        if schema.get("pattern") and not re.search(schema["pattern"], value):
            raise ValueError(f"{path}: unsupported string format")
    if kind in ("integer", "number"):
        low, high = schema.get("minimum", float("-inf")), schema.get("maximum", float("inf"))
        if value < low or value > high:
            bound = f"at least {low}" if value < low else f"at most {high}"
            raise ValueError(f"{path}: {value} given; this field accepts {bound}")
