import json
import logging
import os
from typing import Dict, List
from urllib.request import urlopen

import jsonschema

from jsonschema2ddl.models import Column, Table
from jsonschema2ddl.utils import db_column_name, db_table_name, get_one_schema


class JSONSchemaToDatabase:
    """JSONSchemaToDatabase is the mother class for everything.

    Typically you want to instantiate a `JSONSchemaToPostgres` object, and
    run :func:`create_tables` to create all the tables. Run :func:`create_links`
    to populate all references properly and add foreign keys between tables.
    Optionally you can run :func:`analyze` finally which optimizes the tables.

    Attributes:
        schema (Dict): the schema to translate to tables.
        database_flavor (str): the flavor of the db. One of Postgres or Redshift.
        db_schema_name (str): the name of the schema in the database to create the tables.
        root_table_name (str): Name of the root table for the schema.
        abbreviations (Dict): Dictionary of abbreviations for columns.
        extra_columns (List[Dict]): List of extra columns.
        log_level (str): Log level of the deployment. Default 'DEBUG'.
    """

    logger: logging.Logger = logging.getLogger('JSONSchemaToDatabase')

    def __init__(
            self,
            schema: Dict,
            database_flavor: str = "postgres",
            db_schema_name: str = None,
            abbreviations: Dict = {},  # TODO: Implement abbreviations
            extra_columns: List = [],  # TODO: Implement extra columns
            root_table_name: str = 'root',
            log_level: str = os.getenv('LOG_LEVEL', 'DEBUG')):

        self.logger.setLevel(log_level)
        Table.logger = self.logger.getChild('Table')
        Column.logger = self.logger.getChild('Column')
        Table.logger.setLevel(log_level)
        Column.logger.setLevel(log_level)

        self.schema = schema

        self.database_flavor = database_flavor
        self.db_schema_name = db_schema_name
        self.root_table_name = db_table_name(root_table_name, schema_name=self.db_schema_name)
        self.extra_columns = extra_columns
        self.abbreviations = abbreviations

        self._validate_schema()

        self.table_definitions = self._create_table_definitions()
        self.logger.info('Table definitions initialized')

    def _validate_schema(self):
        """Validates the jsonschema itself against the `$schema` url.

        Currently, some redirections are not supported.

        Raises:
            jsonschema.ValidationError: Schema is invalid
        """
        metaschema_uri = self.schema.get('$schema')
        metaschema_uri = urlopen(metaschema_uri).url

        meta_schema = json.loads(urlopen(metaschema_uri).read())
        jsonschema.validate(instance=self.schema, schema=meta_schema)
        self.logger.debug('Schema is valid')

    def _create_table_definitions(self):
        """Creates the table definitions.

        Returns:
            Dict[str, Table]: A dictionary with tables ids and the tables objects to create.
        """
        # NOTE: create first empty tables to reference later in columns
        table_definitions = dict()
        columns_definitions = dict()
        schema_definitions = self.schema.get('definitions', {})
        for name, object_schema in schema_definitions.items():
            ref = object_schema.get("$id") or f"#/definitions/{name}"
            if 'type' not in object_schema:
                object_schema = get_one_schema(object_schema)

            if object_schema['type'] == 'object':
                table = Table(
                    ref=ref,
                    name=db_table_name(name, schema_name=self.db_schema_name),
                    comment=object_schema.get('comment'),
                    jsonschema_fields=object_schema,
                )
                table_definitions[table.ref] = table
            else:
                # NOTE: Create new column for main table
                column = Column(
                    name=db_column_name(name),
                    database_flavor=self.database_flavor,
                    jsonschema_type=object_schema['type'],
                    jsonschema_fields=object_schema,
                )
                columns_definitions[ref] = column

        root_table = Table(
            ref='root',
            name=self.root_table_name,
            comment=self.schema.get('comment', ""),
            jsonschema_fields=self.schema,
        )
        table_definitions[root_table.ref] = root_table

        for ref, table in table_definitions.items():
            table_definitions[ref] = table.expand_columns(table_definitions, columns_definitions)

        return table_definitions

    def _execute(self, cursor, query, args=None, query_ok_to_print=True):
        """Helper method to execute and debug a query.

        Args:
            cursor (psycopg2.cursor): Cursor object of the db connection.
            query (str): query to execute.
            args (List, optional): List of arguments for the execute command. Defaults to None.
            query_ok_to_print (bool, optional): Defaults to True.
        """
        if query_ok_to_print:
            self.logger.debug(query)
        cursor.execute(query, args)

    def create_tables(
            self,
            conn,
            drop_schema: bool = False,
            drop_tables: bool = False,
            drop_cascade: bool = True,
            auto_commit: bool = False):
        """Create the tables for the schema

        Args:
            conn (psocopg2.connection): Connection object to the db.
            drop_schema (bool, optional): Whether or not drop the schema if exists.
                Defaults to False.
            drop_tables (bool, optional): Whether or not drop the tables if exists.
                Defaults to False.
            drop_cascade (bool, optional): Execute drops with cascade. Defaults to True.
            auto_commit (bool, optional): autocomit after finishing. Defaults to False.
        """
        with conn.cursor() as cursor:
            self.logger.info(f'Creating tables in the schema {self.db_schema_name}')
            if self.db_schema_name is not None:
                if drop_schema:
                    self.logger.info(f'Dropping schema {self.db_schema_name}!!')
                    self._execute(
                        cursor,
                        f'DROP SCHEMA IF EXISTS {self.db_schema_name} {"CASCADE;" if drop_cascade else ";"}'
                    )
                self._execute(cursor, f'CREATE SCHEMA IF NOT EXISTS {self.db_schema_name};')

            self.logger.debug(self.table_definitions.keys())
            for table_ref, table in self.table_definitions.items():
                # FIXME: Move to a separate method
                self.logger.info(f'Trying to create table {table.name}')
                self.logger.debug(table_ref)
                self.logger.debug(table)
                if drop_tables:
                    self.logger.info(f'Dropping table {table.name}!!')
                    self._execute(
                        cursor,
                        f'DROP TABLE IF EXISTS {table.name} {"CASCADE;" if drop_cascade else ";"}'
                    )
                all_cols = [f' "{col.name}" {col.data_type}' for col in table.columns]
                unique_cols = [f'"{col}"' for col in table.columns if col.is_unique]
                create_q = (
                    f"""CREATE TABLE {table.name} ( """
                    f"""{','.join(all_cols)} """
                    f"""{", UNIQUE (" + ','.join(unique_cols) +  ")" if len(unique_cols) > 0 else ""} """
                    f"""{", PRIMARY KEY (" + table.primary_key.name +  ")" if table.primary_key else ""}); """
                )
                self._execute(cursor, create_q)
                if table.comment:
                    self.logger.debug(f'Set the following comment on table {table.name}: {table.comment}')
                    self._execute(cursor, f"COMMENT ON TABLE {table.name} IS '{table.comment}'")
                for col in table.columns:
                    if col.comment:
                        self.logger.debug(f'Set the following comment on column {col.name}: {col.comment}')
                        self._execute(cursor, f'COMMENT ON COLUMN {table.name}."{col.name}" IS ' + f"'{col.comment}'")
                self.logger.info('Table created!')

        if auto_commit:
            conn.commit()

    def create_links(self, conn, auto_commit: bool = True):
        """Adds foreign keys between tables.

        Args:
            conn (psocopg2.connection): connection object.
            auto_commit (bool, Optional): Defaults to False.
        """
        for table_ref, table in self.table_definitions.items():
            for col in table.columns:
                if col.is_fk():
                    fk_q = (
                        f"""ALTER TABLE {table.name} """
                        f"""ADD CONSTRAINT fk_{col.table_ref.name.split('"')[-2]} """  # FIXME: Formatting hack
                        f"""FOREIGN KEY ({col.name}) """
                        f"""REFERENCES {col.table_ref.name} ({col.table_ref.primary_key.name}); """
                    )
                    with conn.cursor() as cursor:
                        self._execute(cursor, fk_q)
                    if auto_commit:
                        conn.commit()
        # raise Exception('OH NO')

    def analyze(self, conn):
        """Runs `analyze` on each table. This improves performance.

        See the `Postgres documentation for Analyze
        <https://www.postgresql.org/docs/9.1/static/sql-analyze.html>`_

        Args:
            conn (psocopg2.connection): connection object.
        """
        self.logger.info('Analyzing tables...')
        with conn.cursor() as cursor:
            for table_ref, table in self.table_definitions.items():
                self.logger.info(f'Launch analyze for {table.name}')
                self._execute(cursor, 'ANALYZE %s' % table.name)


class JSONSchemaToPostgres(JSONSchemaToDatabase):
    """Shorthand for JSONSchemaToDatabase(..., database_flavor='postgres')"""

    def __init__(self, *args, **kwargs):
        kwargs['database_flavor'] = 'postgres'
        return super(JSONSchemaToPostgres, self).__init__(*args, **kwargs)


class JSONSchemaToRedshift(JSONSchemaToDatabase):
    """Shorthand for JSONSchemaToDatabase(..., database_flavor='redshift')"""

    def __init__(self, *args, **kwargs):
        kwargs['database_flavor'] = 'redshift'
        return super(JSONSchemaToRedshift, self).__init__(*args, **kwargs)
