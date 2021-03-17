# JSON Schema ➣ DDL

[![Travis status](https://img.shields.io/travis/clarityai-eng/jsonschema2ddl/master.svg?style=flat)](https://travis-ci.org/clarityai-eng/jsonschema2ddl)

> This repository is a fork. Check out the original project [here](https://github.com/better/jsonschema2ddl)

Create your DDL statements for your database based on your [JSON Schema](http://json-schema.org/).

Postgres and Redshift are supported.

## Installation

Install the latest version with `pip install jsonschema2ddl`.

## Documentation

[JSON Schema](http://json-schema.org/) is a widely used tool. With `jsonschema2ddl` you can take your existing schemas defined with json schema and deploy them in Postgresql and Redshift.

## Usage

Let's start with a jsonschema:

```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Example schema",
    "comment": "the root of everything",
    "definitions": {
        "address": {
            "type": "object",
            "properties": {
                "street_address": {
                    "type": "string"
                },
                "city": {
                    "type": "string"
                },
                "state": {
                    "type": "string"
                }
            }
        }
    },
    "type": "object",
    "properties": {
        "UserId": {
            "type": "integer"
        },
        "UserName": {
            "type": "string"
        },
        "Age": {
            "type": "integer"
        },
        "Address": {
            "$ref": "#/definitions/address"
        }
    }
}
```

Load the schema as a python dictionary to use it:

```python
import json
with open('test/schema.json') as f:
    schema = json.load(f)
```

You will also need a connection object to the database:

```python
pg_uri = 'postgresql://localhost:5432/my_db'
# With psycopg2
import psycopg2
conn = psycopg2.connect(pg_uri)
# OR with sqlalchemy
from sqlalchemy import create_engine
conn = create_engine(pg_uri).raw_connection()
```

Now you can initialize your translators and deploy the tables:

```python
from jsonschema2ddl import JSONSchemaToDatabase

translator = JSONSchemaToDatabase(
    schema,
    schema_name='my_schema',
    root_table_name='my_table',
)

translator.create_tables(conn)
translator.create_links(conn)
translator.analyze(conn)

conn.comit()
```

### Supported features

* A `root` table is created for the schema with the correct types
* Custom PostgreSQL schema to create the tables. The PostgreSQL schema can be drop before deploying the tables.
* Create subtables using the `definitions` sections in the jsonchema document. The name of these tables will be the one defined in the jsonschema. The relationships between the tables can be created as well with the `create_links()` function. This also requires to have some column as the primary key. You can specify this column with the `pk` field in the definition of the schema. If there are no `pk` column defined, a default `id` column will be created for the table.
* Following types are supported:
  * `boolean` -> converted to type `bool`.
  * `number` -> converted to type `float`.
  * `string` -> converted to type `varchar({size})`. The size defaults to 256, and can be specified using the `maxLength` field in the definition.
    * If the format for the string type is defined to `date-time`, it is converted to `timestamptz` type.
    * If the format for the string type is defined to `date`, it is converted to `date` type.
  * `timestamp` -> converted to type `timestamptz`.
  * `enum` -> converted to type `text`.
  * `integer` -> converted to type `bigint`.
  * `date` -> converted to type `date`.
  * `link` -> converted to type `integer`.
  * `object` -> converted to type `json`.
  * `id` -> converted to type `serial` in postgresql. For redshift, it is converted to `int identity(1, 1) not null`.
* Schema itself is validated against the `$schema` definition uri.

### Known Limitations and Roadmap of New Features

* Specify constraints in the jsonschema.
* Specify indexes in the jsonschema.
* Create enums in postgresql.
* Support pattern constrints
* Support redirects when validating the `$schema`
* Support nested refs in schema

## Other

* This repo uses the [MIT license](https://github.com/better/jsonschema2ddl/blob/master/LICENSE).
