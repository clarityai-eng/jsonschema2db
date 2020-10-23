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
    'object': 'json',
    'id': 'serial',
}

REDSHIFT_TYPES = {
    **POSTGRES_TYPES,
    'object': 'text',
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
