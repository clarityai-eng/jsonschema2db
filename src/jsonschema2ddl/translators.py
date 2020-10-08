import csv
import datetime
import os
import random
import sys
import tempfile
import warnings
from typing import Dict, List, Tuple

import change_case
import iso8601

POSTGRES_TYPES = {
    'boolean': 'bool',
    'number': 'float',
    'string': 'text',
    'enum': 'text',
    'integer': 'bigint',
    'timestamp': 'timestamptz',
    'date': 'date',
    'link': 'integer',
}

ID_TYPES = {
    'postgres': 'serial',
    'redshift': 'int identity(1, 1) not null',
}


class JSONSchemaToDatabase:
    """JSONSchemaToDatabase is the mother class for everything.

    Typically you want to instantiate a `JSONSchemaToPostgres` object, and
    run :func:`create_tables` to create all the tables. After that, insert
    all data using :func:`insert_items`. Once you're done inserting,
    run :func:`create_links` to populate all references properly and add
    foreign keys between tables. Optionally you can run :func:`analyze` finally
    which optimizes the tables.


    Args:
        schema (Dict): The JSON schema, as a native Python dict
        database_flavor (str, optional): Either "postgres" or "redshift".
            Defaults to "postgres".
        postgres_schema (str, optional): A string denoting a postgres schema
            (namespace) under which all tables will be created. Defaults to None.
        debug (bool, optional): Set this to True if you want all queries to be
            printed to stderr. Defaults to False.
        id_cols (List, optional): The name of the main object key. This will
            be translated as a Primary Key. Defaults to None.
        unique_cols (List, optional): List of columns with unique connstraint.
            Defaults to []
        abbreviations (Dict, optional): A string to string mapping containing
            replacements applied to each part of the path. Defaults to {}.
        extra_columns (List, optional): A list of pairs representing extra
            columns in the root table. The format is ('column_name', 'type').
            Defaults to [].
        root_table (str, optional): Name of the root table. Defaults to 'root'.
        s3_client ([type], optional): (optional, Redshift only) A boto3 client
            object used for copying data through S3 (if not provided then it
            will use INSERT statements, which can be very slow). Defaults to None.
        s3_bucket ([type], optional): (optional, Redshift only) Required with
            s3_client. Defaults to None.
        s3_prefix (str, optional): (optional, Redshift only) Optional subdirectory
            within the S3 bucket. Defaults to 'jsonschema2ddl'.
        s3_iam_arn ([type], optional): (optional, Redshift only) Extra IAM
            argument. Defaults to None.
    """

    def __init__(
            self,
            schema: Dict,
            database_flavor: str = "postgres",
            postgres_schema: str = None,
            debug: bool = False,
            id_cols: List = [],
            unique_cols: List = [],
            abbreviations: Dict = {},
            extra_columns: List = [],
            root_table: str = 'root',
            s3_client=None,
            s3_bucket=None,
            s3_prefix: str = 'jsonschema2ddl',
            s3_iam_arn=None):
        self._database_flavor = database_flavor
        self._debug = debug
        self._table_definitions = {}
        self._links = {}
        self._backlinks = {}
        self._postgres_schema = postgres_schema
        self._id_cols = [change_case.ChangeCase.camel_to_snake(c) for c in id_cols]
        self._unique_cols = [change_case.ChangeCase.camel_to_snake(c) for c in unique_cols]
        self._abbreviations = abbreviations
        self._extra_columns = extra_columns
        self._table_comments = {}
        self._column_comments = {}
        self._root_table = root_table

        # Redshift-specific properties
        self._s3_client = s3_client
        self._s3_bucket = s3_bucket
        self._s3_prefix = s3_prefix
        self._s3_iam_arn = s3_iam_arn

        # Various counters used for diagnostics during insertions
        self.failure_count = {}  # path -> count
        self.json_path_count = {}  # json path -> count

        # Walk the schema and build up the translation tables
        self._translation_tree = self._traverse(schema, schema, table=self._root_table, comment=schema.get('comment'))

        # Need to compile all the backlinks that uniquely identify a parent and add columns for them
        for child_table in self._backlinks:
            if len(self._backlinks[child_table]) != 1:
                # Need a unique path on the parent table for this to make sense
                continue
            parent_table, ref_col_name, _ = list(self._backlinks[child_table])[0]
            self._backlinks[child_table] = (parent_table, ref_col_name)
            self._table_definitions[child_table][ref_col_name] = 'link'
            self._links.setdefault(child_table, {})[ref_col_name] = (None, parent_table)

        # Construct tables and columns
        self._table_columns = {}
        max_column_length = {'postgres': 63, 'redshift': 127}[self._database_flavor]

        for col, col_type in self._extra_columns:
            if 0 < len(col) <= max_column_length:
                self._table_definitions[self._root_table][col] = col_type

        for table, column_types in self._table_definitions.items():
            for column in column_types.keys():
                if len(column) > max_column_length:
                    warnings.warn('Ignoring_column because it is too long: %s.%s' % (table, column))
            columns = sorted(col for col in column_types.keys() if 0 < len(col) <= max_column_length)
            self._table_columns[table] = columns

    def _table_name(self, path):
        return '__'.join(change_case.ChangeCase.camel_to_snake(self._abbreviations.get(p, p)) for p in path)

    def _column_name(self, path):
        return self._table_name(path)  # same

    def _execute(self, cursor, query, args=None, query_ok_to_print=True, dst=sys.stderr):
        if self._debug and query_ok_to_print:
            print(query, file=dst)
        cursor.execute(query, args)

    def _traverse(
            self,
            schema,
            tree,
            path: Tuple = tuple(),
            table='root',
            parent=None,
            comment=None,
            json_path: Tuple = tuple()) -> Dict:
        """Computes a bunch of stuff

        1. A list of tables and columns (used to create tables dynamically)
        2. A tree (dicts of dicts) with a mapping for each fact into tables (used to map data)
        3. Links between entities

        Args:
            schema ([type]): [description]
            tree ([type]): [description]
            path (Tuple, optional): [description]. Defaults to tuple().
            table (str, optional): [description]. Defaults to 'root'.
            parent ([type], optional): [description]. Defaults to None.
            comment ([type], optional): [description]. Defaults to None.
            json_path (Tuple, optional): [description]. Defaults to tuple().

        Returns:
            Dict: [description]
        """
        if type(tree) != dict:
            warnings.warn('%s.%s: Broken subtree' % (table, self._column_name(path)))
            return

        if parent is not None:
            self._backlinks.setdefault(table, set()).add(parent)

        if table not in self._table_definitions:
            self._table_definitions[table] = {}
            if comment:
                self._table_comments[table] = comment

        definition = None
        new_json_path = json_path
        while '$ref' in tree:
            ref = tree['$ref']
            p = ref.lstrip('#').lstrip('/').split('/')
            tree = schema
            for elem in p:
                if elem not in tree:
                    warnings.warn('%s.%s: Broken definition: %s' % (table, self._column_name(path), ref))
                    return
                tree = tree[elem]
            new_json_path = ('#',) + tuple(p)
            definition = p[-1]  # TODO(erikbern): we should just make this a boolean variable

        special_keys = set(tree.keys()).intersection(['oneOf', 'allOf', 'anyOf'])
        if special_keys:
            res = {}
            for p in special_keys:
                for q in tree[p]:
                    res.update(self._traverse(schema, q, path, table, json_path=new_json_path))
            return res  # This is a special node, don't store any more information
        elif 'enum' in tree:
            self._table_definitions[table][self._column_name(path)] = 'enum'
            if 'comment' in tree:
                self._column_comments.setdefault(table, {})[self._column_name(path)] = tree['comment']
            res = {'_column': self._column_name(path), '_type': 'enum'}
        elif 'type' not in tree:
            res = {}
            warnings.warn('%s.%s: Type info missing' % (table, self._column_name(path)))
        elif tree['type'] == 'object':
            print('object:', tree)
            res = {}
            if 'patternProperties' in tree:
                # Always create a new table for the pattern properties
                if len(tree['patternProperties']) > 1:
                    warnings.warn('%s.%s: Multiple patternProperties, will ignore all except first' % (table, self._column_name(path)))
                for p in tree['patternProperties']:
                    ref_col_name = table + '_id'
                    res['*'] = self._traverse(schema, tree['patternProperties'][p], tuple(), self._table_name(path), (table, ref_col_name, self._column_name(path)), tree.get('comment'), new_json_path + (p,))
                    break
            elif 'properties' in tree:
                if definition:
                    # This is a shared definition, so create a new table (if not already exists)
                    if path == tuple():
                        ref_col_name = self._table_name([definition]) + '_id'
                    else:
                        ref_col_name = self._column_name(path) + '_id'
                    for p in tree['properties']:
                        res[p] = self._traverse(schema, tree['properties'][p], (p, ), self._table_name([definition]), (table, ref_col_name, self._column_name(path)), tree.get('comment'), new_json_path + (p,))
                    self._table_definitions[table][ref_col_name] = 'link'
                    self._links.setdefault(table, {})[ref_col_name] = ('/'.join(path), self._table_name([definition]))
                else:
                    # Standard object, just traverse recursively
                    for p in tree['properties']:
                        res[p] = self._traverse(schema, tree['properties'][p], path + (p,), table, parent, tree.get('comment'), new_json_path + (p,))
            else:
                warnings.warn('%s.%s: Object with neither properties nor patternProperties' % (table, self._column_name(path)))
        else:
            if tree['type'] == 'null':
                res = {}
            elif tree['type'] not in ['string', 'boolean', 'number', 'integer']:
                warnings.warn('%s.%s: Type error: %s' % (table, self._column_name(path), tree['type']))
                res = {}
            else:
                if definition in ['date', 'timestamp']:
                    t = definition
                else:
                    t = tree['type']
                self._table_definitions[table][self._column_name(path)] = t
                if 'comment' in tree:
                    self._column_comments.setdefault(table, {})[self._column_name(path)] = tree['comment']
                res = {'_column': self._column_name(path), '_type': t}

        res['_table'] = table
        res['_suffix'] = '/'.join(path)
        res['_json_path'] = '/'.join(json_path)
        self.json_path_count['/'.join(json_path)] = 0

        return res

    def _coerce_type(self, t: str, value) -> Tuple[str, str]:
        """Returns a two-tuple (is_valid, new_value) where new_value is properly coerced.

        Returns:
            Tuple[str, str]: (is_valid, new_value)
        """
        try:
            if t == 'number':
                return type(value) != bool, float(value)
            elif t == 'integer':
                return type(value) != bool, int(value)
            elif t == 'boolean':
                return type(value) == bool, value
            elif t == 'timestamp':
                if type(value) == datetime.datetime:
                    return True, value
                return True, iso8601.parse_date(value)
            elif t == 'date':
                if type(value) == datetime.date:
                    return True, value
                return True, datetime.date(*(int(z) for z in value.split('-')))
            elif t == 'string':
                # Allow coercing ints/floats, but nothing else
                return type(value) in [str, int, float], str(value)
            elif t == 'enum':
                return type(value) == str, str(value)
        except Exception as e:
            print("Error coercing types: ", e)
        return False, None

    def _flatten_dict(self, data, res=None, path=tuple()):
        if res is None:
            res = []
        if type(data) == dict:
            for k, v in data.items():
                self._flatten_dict(v, res, path + (k,))
        else:
            res.append((path, data))
        return res

    def _postgres_table_name(self, table):
        if self._postgres_schema is None:
            return '"%s"' % table
        else:
            return '"%s"."%s"' % (self._postgres_schema, table)

    def create_tables(
            self,
            conn,
            drop_schema: bool = False,
            drop_tables: bool = False,
            drop_cascade: bool = True,
            auto_commit: bool = False):
        """Creates tables

        Args:
            conn (conn): connection object
        """
        with conn.cursor() as cursor:
            if self._postgres_schema is not None:
                if drop_schema:
                    self._execute(
                        cursor,
                        f'DROP SCHEMA IF EXISTS {self._postgres_schema} {"CASCADE;" if drop_cascade else ";"}'
                    )
                self._execute(cursor, f'CREATE SCHEMA IF NOT EXISTS {self._postgres_schema};')
            for table, columns in self._table_columns.items():
                types = [self._table_definitions[table][column] for column in columns]
                # id_data_type = ID_TYPES[self._database_flavor]
                table_name = self._postgres_table_name(table)
                if drop_tables:
                    self._execute(
                        cursor,
                        f'DROP TABLE IF EXISTS {table_name} {"CASCADE;" if drop_cascade else ";"}'
                    )
                unique_cols = ','.join(f'"{c}"' for c in self._unique_cols if c in columns)
                primary_key_cols = ','.join(f'"{c}"' for c in self._id_cols if c in columns)
                all_cols = ','.join('"%s" %s ' % (c, POSTGRES_TYPES[t]) for c, t in zip(columns, types))
                create_q = f"""CREATE TABLE {table_name} (
                        {all_cols}
                        {", UNIQUE (" + unique_cols +  ")" if len(unique_cols) > 0 else ""}
                        {", PRIMARY KEY (" + primary_key_cols +  ")" if len(primary_key_cols) > 0 else ""});
                    """
                self._execute(cursor, create_q)
                if table in self._table_comments:
                    self._execute(cursor, 'COMMENT ON TABLE %s IS %%s' % table_name, (self._table_comments[table],))
                for c in columns:
                    if c in self._column_comments.get(table, {}):
                        self._execute(cursor, 'COMMENT ON COLUMN %s."%s" IS %%s' % (table_name, c), (self._column_comments[table][c],))
        if auto_commit:
            conn.commit()

    # FIXME: Create Links for subtables
    def create_links(self, conn):
        """Adds foreign keys between tables.

        Args:
            conn ([type]): connection object
        """
        from warnings import warn
        warn("This function doesn't work with the current implementation! Skiping")
        return -1
        for from_table, cols in self._links.items():
            for ref_col_name, (prefix, to_table) in cols.items():
                if from_table not in self._table_columns or to_table not in self._table_columns:
                    continue
                args = {
                    'from_table': self._postgres_table_name(from_table),
                    'to_table': self._postgres_table_name(to_table),
                    'ref_col': ref_col_name,
                    'id_cols': ','.join(self._id_cols),
                    'prefix_col': self._prefix_col_name,
                    'prefix': prefix,
                }
                update_q = """UPDATE %(from_table)s
                    SET "%(ref_col)s" = to_table.id FROM (
                        SELECT "%(id_cols)s", "%(prefix_col)s", FROM %(to_table)s
                    ) to_table
                    """ % args
                if prefix:
                    # Forward reference from table to a definition
                    update_q += """
                        WHERE %(from_table)s."%(item_col)s" = to_table."%(item_col)s"
                            AND %(from_table)s."%(prefix_col)s" || \'/%(prefix)s\' = to_table."%(prefix_col)s"
                        """ % args
                else:
                    # Backward definition from a table to its patternProperty parent
                    update_q += """
                        WHERE %(from_table)s."%(item_col)s" = to_table."%(item_col)s"
                            AND strpos(%(from_table)s."%(prefix_col)s", to_table."%(prefix_col)s") = 1
                        """ % args

                alter_q = """
                    ALTER TABLE %(from_table)s
                        ADD CONSTRAINT fk_%(ref_col)s FOREIGN KEY ("%(ref_col)s") REFERENCES %(to_table)s (%(id_cols)s)
                    """ % args
                with conn.cursor() as cursor:
                    self._execute(cursor, update_q)
                    self._execute(cursor, alter_q)

    def analyze(self, conn):
        """Runs `analyze` on each table. This improves performance.

        See the `Postgres documentation for Analyze
        <https://www.postgresql.org/docs/9.1/static/sql-analyze.html>`_

        Args:
            conn ([type]): connection object
        """
        with conn.cursor() as cursor:
            for table in self._table_columns.keys():
                self._execute(cursor, 'ANALYZE %s' % self._postgres_table_name(table))


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
