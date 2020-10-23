from change_case import ChangeCase


def db_table_name(table_name, schema_name=None):
    table_name = ChangeCase.camel_to_snake(table_name)
    if schema_name is None:
        return f'"{table_name}"'
    else:
        return f'"{schema_name}"."{table_name}"'


def db_column_name(col_name):
    return ChangeCase.camel_to_snake(col_name)
