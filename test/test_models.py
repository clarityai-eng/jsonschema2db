import pytest

from jsonschema2ddl.models import Column, FKColumn, Table


def test_column():
    simple = {"type": "integer"}

    column = Column(name='simple', jsonschema_type=simple['type'], jsonschema_fields=simple)
    assert column.name == 'simple'
    assert column.data_type == 'bigint'

    simple = {"type": "string"}

    column = Column(name='simple', jsonschema_type=simple['type'], jsonschema_fields=simple)
    assert column.name == 'simple'
    assert column.data_type == 'varchar(256)'

    simple = {"type": "string", "maxLength": 1024}

    column = Column(name='simple', jsonschema_type=simple['type'], jsonschema_fields=simple)
    assert column.name == 'simple'
    assert column.data_type == 'varchar(1024)'


def test_column_hash():
    simple1 = {"type": "integer"}
    simple2 = {"type": "string"}
    columns = set()
    column1 = Column(name='simple1', jsonschema_type=simple1['type'])
    column2 = Column(name='simple2', jsonschema_type=simple2['type'])

    columns.add(column1)
    columns.add(column2)
    columns.add(column2)

    assert len(columns) == 2


def test_table(schema_flat):
    root_table = Table(
        ref='root',
        name='root',
        jsonschema_fields=schema_flat,
    )

    assert root_table.name == 'root'
    assert root_table.ref == 'root'

    root_table.expand_columns(table_definitions={'root': root_table})
    assert len(root_table.columns) == len(schema_flat['properties'])


@pytest.mark.skip(reason='Test not implemented')
def test_fkcolumn():
    # TODO: Create table and check the data type
    assert False
