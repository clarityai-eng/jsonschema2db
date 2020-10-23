from jsonschema2ddl.utils import db_column_name, db_table_name


def test_name_changes():

    assert db_column_name('IAmGroot') == "i_am_groot"
    assert db_table_name('IAmGroot') == '"i_am_groot"'
    assert db_table_name('IAmGroot', schema_name='gardians') == '"gardians"."i_am_groot"'
