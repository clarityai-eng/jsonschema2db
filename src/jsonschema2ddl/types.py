from enum import Enum


# TODO: Define the types as enum
class Type(Enum):
    pass


POSTGRES_TYPES = {
    'boolean': 'bool',
    'number': 'float',
    'string': 'varchar({})',
    'enum': 'text',
    'integer': 'bigint',
    'timestamp': 'timestamptz',
    'date': 'date',
    'link': 'integer',
    'array': 'json',
    'object': 'json',
    'id': 'serial',
}

REDSHIFT_TYPES = {
    **POSTGRES_TYPES,
    'array': 'varchar(1024)',
    'object': 'varchar(1024)',
    'id': 'int identity(1, 1) not null',
}

COLUMNS_TYPES = {
    'postgres': POSTGRES_TYPES,
    'redshift': REDSHIFT_TYPES,
}

FK_TYPES = {
    'serial': 'bigint',
    'int identity(1, 1) not null': 'bigint',
}

COLUMNS_TYPES_PREFERENCE = {
    'boolean': 0,
    'bool': 0,
    'enum': 1,
    'link': 2,
    'integer': 3,
    'bigint': 4,
    'number': 5,
    'float': 5,
    'date': 5,
    'timestamp': 6,
    'timestamptz': 6,
    'array': 7,
    'text': 8,
    'string': 8,
    'object': 9,
    'json': 9,
    'id': 10,
    'serial': 10,
}
