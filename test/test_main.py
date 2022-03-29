import datetime

import pytest
from sqlalchemy.sql import text

from jsonschema2ddl import JSONSchemaToDatabase


def query(con, q):
    cur = con.cursor()
    cur.execute(q)
    return cur.fetchall()


def test_flat_schema(db, schema_flat):
    connection = db["connection"]
    translator = JSONSchemaToDatabase(
        schema_flat,
        db_schema_name="schm",
        root_table_name="my_table",
    )

    translator.create_tables(connection, auto_commit=True)
    translator.create_links(connection)
    translator.analyze(connection)

    with db["engine"].connect() as conn:
        data = (
            {"user_id": 1, "user_name": "john", "age": 20, "address": "USA"},
            {"user_id": 2, "user_name": "doe", "age": 21, "address": "USA"},
        )
        statement = text(
            """
            INSERT INTO "schm"."my_table" (user_id, user_name, age, address)
                VALUES(:user_id, :user_name, :age, :address)"""
        )
        for line in data:
            conn.execute(statement, **line)

        result = conn.execute('SELECT * FROM "schm"."my_table"')
        rows = [row for row in result]
        assert len(rows) == 2


def test_schema(db, schema):
    connection = db["connection"]
    translator = JSONSchemaToDatabase(
        schema,
        db_schema_name="schm",
        root_table_name="my_table",
    )

    translator.create_tables(connection, auto_commit=True)
    translator.create_links(connection)
    translator.analyze(connection)

    with db["engine"].connect() as conn:
        data = (
            {"street_address": "street1", "city": "LA", "state": "CA"},
            {"street_address": "street2", "city": "SF", "state": "CA"},
        )
        statement = text(
            """
            INSERT INTO "schm"."address" (street_address, city, state)
                VALUES(:street_address, :city, :state)"""
        )
        for line in data:
            conn.execute(statement, **line)

        result = conn.execute('SELECT * FROM "schm"."address"')
        rows = [row for row in result]
        assert len(rows) == 2

        data = (
            {"user_id": 1, "user_name": "john", "age": 20, "address": 1},
            {"user_id": 2, "user_name": "doe", "age": 21, "address": 2},
        )
        statement = text(
            """
            INSERT INTO "schm"."my_table" (user_id, user_name, age, address)
                VALUES(:user_id, :user_name, :age, :address)"""
        )
        for line in data:
            conn.execute(statement, **line)

        result = conn.execute('SELECT * FROM "schm"."my_table"')
        rows = [row for row in result]

        assert len(rows) == 2
        bad_data = {"user_id": 3, "user_name": "doe", "age": 21, "address": 1000}
        with pytest.raises(Exception):
            conn.execute(statement, **bad_data)

        result = conn.execute('SELECT * FROM "schm"."my_table"')
        rows = [row for row in result]

        assert len(rows) == 2


@pytest.mark.skip(reason="Current implementation doesn't support extra columns")
def test_extra_columns(db, schema_flat):
    connection = db["connection"]
    translator = JSONSchemaToDatabase(
        schema_flat,
        db_schema_name="schm",
        root_table_name="my_table",
        extra_columns=[("points", "integer")],
    )

    translator.create_tables(connection, auto_commit=True)
    # translator.create_links(connection)
    translator.analyze(connection)

    with db["engine"].connect() as conn:
        data = (
            {
                "user_id": 1,
                "user_name": "john",
                "age": 20,
                "address": "USA",
                "points": 100,
            },
            {
                "user_id": 2,
                "user_name": "doe",
                "age": 21,
                "address": "USA",
                "points": 100,
            },
        )
        statement = text(
            """
            INSERT INTO "schm"."my_table" (user_id, user_name, age, address, points)
                VALUES(:user_id, :user_name, :age, :address, :points)"""
        )
        for line in data:
            conn.execute(statement, **line)

        result = conn.execute('SELECT * FROM "schm"."my_table"')
        rows = [row for row in result]
        assert len(rows) == 2


def test_comments(schema_long_names):
    translator = JSONSchemaToDatabase(schema_long_names)

    # A bit ugly to look at private members, but pulling comments out of postgres is a pain
    table_comments = {
        "root": "the root of everything",
        "basic_address": "This is an address",
    }
    column_comments = {"basic_address": {"city": "This is a city"}}
    assert translator.table_definitions["root"].comment == table_comments["root"]
    assert translator.table_definitions["#/definitions/basicAddress"].comment == table_comments["basic_address"]
    columns = translator.table_definitions["#/definitions/basicAddress"].columns
    column_comments = {c.name: c.comment for c in columns if c.comment != ""}
    assert column_comments == column_comments


def test_time_types(db, schema_time):
    connection = db["connection"]
    translator = JSONSchemaToDatabase(schema_time)

    translator.create_tables(connection, auto_commit=True)

    with db["engine"].connect() as conn:
        data = (
            {
                "ts": datetime.datetime(2018, 2, 3, 12, 45, 56),
                "d": datetime.date(2018, 7, 8),
            },
            {"ts": "2017-02-03T01:23:45Z", "d": "2013-03-02"},
        )
        statement = text("""INSERT INTO root (ts, d) VALUES(:ts, :d)""")
        for line in data:
            conn.execute(statement, **line)

        result = conn.execute("SELECT ts, d FROM root")
        rows = [(ts.strftime("%Y-%m-%dT%H:%M:%SZ"), d.strftime("%Y-%m-%dT%H:%M:%SZ")) for ts, d in result]
        assert len(rows) == 2
        assert rows == [
            (
                datetime.datetime(2018, 2, 3, 12, 45, 56).strftime("%Y-%m-%dT%H:%M:%SZ"),
                datetime.date(2018, 7, 8).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
            (
                datetime.datetime(2017, 2, 3, 1, 23, 45).strftime("%Y-%m-%dT%H:%M:%SZ"),
                datetime.date(2013, 3, 2).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
        ]


@pytest.mark.skip(reason="Current implementation doesn't support nested refs")
def test_refs(db, schema_refs):
    connection = db["connection"]
    translator = JSONSchemaToDatabase(schema_refs)

    translator.create_tables(connection)
    assert list(query(connection, "select col from c")) == []  # Just make sure table exists
