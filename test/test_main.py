import datetime
import json

from sqlalchemy.sql import text

from jsonschema2ddl import JSONSchemaToPostgres


def query(con, q):
    cur = con.cursor()
    cur.execute(q)
    return cur.fetchall()


def test_flat_schema(db):
    connection = db["connection"]
    schema = json.load(open('test/test_schema_flat.json'))
    translator = JSONSchemaToPostgres(
        schema,
        postgres_schema='schm',
        root_table='my_table',
        id_cols=["UserId"],
        debug=True,
    )

    translator.create_tables(connection, auto_commit=True)
    # FIXME: Create Links for subtables
    # translator.create_links(connection)
    translator.analyze(connection)

    with db['engine'].connect() as conn:
        data = (
            {"user_id": 1, "user_name": "john", "age": 20, "address": "USA"},
            {"user_id": 2, "user_name": "doe", "age": 21, "address": "USA"}
        )
        statement = text("""
            INSERT INTO "schm"."my_table" (user_id, user_name, age, address)
                VALUES(:user_id, :user_name, :age, :address)""")
        for line in data:
            conn.execute(statement, **line)

        result = conn.execute('SELECT * FROM "schm"."my_table"')
        rows = [row for row in result]
        assert len(rows) == 2


def test_extra_columns(db):
    connection = db["connection"]
    schema = json.load(open('test/test_schema_flat.json'))
    translator = JSONSchemaToPostgres(
        schema,
        postgres_schema='schm',
        root_table='my_table',
        id_cols=["UserId"],
        extra_columns=[('points', 'integer')],
        debug=True,
    )

    translator.create_tables(connection, auto_commit=True)
    # FIXME: Create Links for subtables
    # translator.create_links(connection)
    translator.analyze(connection)

    with db['engine'].connect() as conn:
        data = (
            {"user_id": 1, "user_name": "john", "age": 20, "address": "USA", "points": 100},
            {"user_id": 2, "user_name": "doe", "age": 21, "address": "USA", "points": 100}
        )
        statement = text("""
            INSERT INTO "schm"."my_table" (user_id, user_name, age, address, points)
                VALUES(:user_id, :user_name, :age, :address, :points)""")
        for line in data:
            conn.execute(statement, **line)

        result = conn.execute('SELECT * FROM "schm"."my_table"')
        rows = [row for row in result]
        assert len(rows) == 2


def test_comments():
    schema = json.load(open('test/test_schema.json'))
    translator = JSONSchemaToPostgres(schema, debug=True)

    # A bit ugly to look at private members, but pulling comments out of postgres is a pain
    assert translator._table_comments == {
        'root': 'the root of everything',
        'basic_address': 'This is an address',
    }
    assert translator._column_comments == {
        'basic_address': {
            'city': 'This is a city'
        }
    }


def test_time_types(db):
    connection = db["connection"]
    schema = json.load(open('test/test_time_schema.json'))
    translator = JSONSchemaToPostgres(schema, debug=True)

    translator.create_tables(connection, auto_commit=True)
    with db['engine'].connect() as conn:
        data = (
            {'ts': datetime.datetime(2018, 2, 3, 12, 45, 56), 'd': datetime.date(2018, 7, 8)},
            {'ts': '2017-02-03T01:23:45Z', 'd': '2013-03-02'},
        )
        statement = text("""INSERT INTO root (ts, d) VALUES(:ts, :d)""")
        for line in data:
            conn.execute(statement, **line)

        result = conn.execute('SELECT ts, d FROM root')
        rows = [(ts.strftime("%Y-%m-%dT%H:%M:%SZ"), d.strftime("%Y-%m-%dT%H:%M:%SZ")) for ts, d in result]
        assert len(rows) == 2
        assert rows == [
            (datetime.datetime(2018, 2, 3, 12, 45, 56).strftime("%Y-%m-%dT%H:%M:%SZ"), datetime.date(2018, 7, 8).strftime("%Y-%m-%dT%H:%M:%SZ")),
            (datetime.datetime(2017, 2, 3, 1, 23, 45).strftime("%Y-%m-%dT%H:%M:%SZ"), datetime.date(2013, 3, 2).strftime("%Y-%m-%dT%H:%M:%SZ"))
        ]


def test_refs(db):
    connection = db["connection"]
    schema = json.load(open('test/test_refs.json'))
    translator = JSONSchemaToPostgres(schema, debug=True)

    translator.create_tables(connection)
    assert list(query(connection, 'select col from c')) == []  # Just make sure table exists
