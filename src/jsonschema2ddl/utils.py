from typing import Dict, Tuple

from change_case import ChangeCase
from jsonschema import ValidationError

from jsonschema2ddl.types import COLUMNS_TYPES_PREFERENCE


def db_table_name(table_name: str, schema_name: str = None) -> str:
    table_name = ChangeCase.camel_to_snake(table_name)
    if schema_name is None:
        return f'"{table_name}"'
    else:
        return f'"{schema_name}"."{table_name}"'


def db_column_name(col_name: str) -> str:
    return ChangeCase.camel_to_snake(col_name)


def get_one_schema(object_schema) -> Dict:
    """Get one schema from a list of 'allOf', 'anyOf', 'oneOf'."""
    types = object_schema.get("allOf", object_schema.get("anyOf", object_schema.get("oneOf", [])))
    if not types:
        raise ValidationError("Neither 'type', 'allOf', 'anyOf', 'oneOf' defined for field. Aborting!")

    def get_type_preference(type_definition: Dict) -> Tuple[Dict, float]:
        schema_type: str = type_definition["type"]
        if "format" in type_definition and type_definition["format"] in COLUMNS_TYPES_PREFERENCE:
            schema_type: str = type_definition["format"]
        return type_definition, COLUMNS_TYPES_PREFERENCE[schema_type]

    types_with_preference = map(get_type_preference, types)
    max_preference_type = max(types_with_preference, key=lambda x: x[1])[0]
    return max_preference_type
