import datetime as dt

import pytest
from sqlalchemy import create_engine
from testcontainers.postgres import PostgresContainer

now = dt.datetime.now()


@pytest.fixture
def datetime_now():
    return now


@pytest.fixture
def db(scope="session"):
    with PostgresContainer("postgres:11.4") as postgres:
        engine = create_engine(postgres.get_connection_url())
        connection = engine.raw_connection()
        yield {
            "connection": connection,
            "engine": engine,
        }
        connection.close()
