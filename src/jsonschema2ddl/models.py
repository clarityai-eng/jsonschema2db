import logging
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Set

from jsonschema2ddl.types import COLUMNS_TYPES, FK_TYPES
from jsonschema2ddl.utils import db_column_name


@dataclass
class Column:
    name: str
    database_flavor: str = "postgres"
    comment: str = field(default_factory=str, repr=False)
    constraints: Dict = field(default_factory=dict, repr=False)
    jsonschema_type: str = field(default_factory=str, repr=False)
    jsonschema_fields: Dict = field(default_factory=dict, repr=False)

    logger: logging.Logger = field(default=logging.getLogger('Column'), repr=False)

    @property
    def max_lenght(self) -> int:
        return self.jsonschema_fields.get('maxLength', 256)

    @property
    def data_type(self) -> str:
        if 'format' in self.jsonschema_fields:
            # FIXME: catch this case as a more generic type
            if self.jsonschema_fields['format'] == 'date-time':
                return 'timestamptz'
            elif self.jsonschema_fields['format'] == 'date':
                return 'date'
        return COLUMNS_TYPES[self.database_flavor][self.jsonschema_type].format(self.max_lenght)

    # FIXME: Property or simple function?
    @property
    def is_pk(self) -> bool:
        return self.jsonschema_fields.get('pk', False)

    # FIXME: Property or simple function?
    @property
    def is_index(self) -> bool:
        return self.jsonschema_fields.get('index', False)

    # FIXME: Property or simple function?
    @property
    def is_unique(self) -> bool:
        return self.jsonschema_fields.get('unique', False)

    @staticmethod
    def is_fk() -> bool:
        """Returns true if the column is a foreign key.

        Returns:
            bool: True if it is foreign key
        """
        return False

    def __hash__(self):
        return hash(self.name)

    # FIXME: Avoid overwritting the the repr method
    # NOTE: Overwrite dataclass method to show data_type property
    def __repr__(self):
        return f"Column(name={self.name} data_type={self.data_type})"


@dataclass
class Table:
    ref: str
    name: str
    database_flavor: str = "postgres"
    columns: Set[Column] = field(default_factory=set)
    primary_key: Column = None
    comment: str = None
    indexes: List[str] = field(default_factory=list)
    unique_columns: List[str] = field(default_factory=list)
    jsonschema_fields: Dict = field(default_factory=dict, repr=False)

    logger: logging.Logger = field(default=logging.getLogger('Table'), repr=False)
    _expanded: bool = field(default=False, repr=False)

    def expand_columns(
            self,
            table_definitions: Dict = dict(),
            columns_definitions: Dict = dict(),
            referenced: bool = False) -> Dict:
        if self._expanded:
            self.logger.info('Already expanded table. Skiping...')
            return self
        for col_name, col_object in self.jsonschema_fields.get('properties').items():
            self.logger.debug(f'Creating column {col_name}')
            col_name = db_column_name(col_name)
            self.logger.debug(f'Renamed column to {col_name}')
            if '$ref' in col_object:
                self.logger.debug(f"Expanding {col_name} reference {col_object['$ref']}")
                self.logger.debug(table_definitions)
                if col_object['$ref'] in table_definitions:
                    ref = col_object['$ref']
                    self.logger.debug(f'Column is a FK! Expanding {ref} before continue...')
                    table_definitions[ref] = table_definitions[ref].expand_columns(
                        table_definitions=table_definitions,
                        referenced=True)
                    col = FKColumn(
                        table_ref=table_definitions[ref],
                        name=col_name,
                        database_flavor=self.database_flavor,
                    )
                elif col_object['$ref'] in columns_definitions:
                    logging.debug(
                        'Column ref a type that is not a object. '
                        'Copy Column from columns definitions')
                    ref = col_object['$ref']
                    ref_col = columns_definitions[ref]
                    col_as_dict = {**asdict(ref_col), 'name': col_name}
                    col = Column(**col_as_dict)
                else:
                    logging.debug('Skipping ref as it is not in table definitions neither in columns definitions')
                    continue
            else:
                col = Column(
                    name=col_name,
                    database_flavor=self.database_flavor,
                    jsonschema_type=col_object['type'],
                    jsonschema_fields=col_object,
                )
            self.columns.add(col)
            if col.is_pk:
                self.primary_key = col

            self.logger.info(f'New created column {col}')

        if referenced and not self.primary_key:
            self.logger.info('Creating id column for the table in order to reference it as PK')
            col = Column(
                name='id',
                database_flavor=self.database_flavor,
                jsonschema_type='id',
            )
            self.columns.add(col)
            self.primary_key = col

        return self


@dataclass(eq=False)
class FKColumn(Column):
    table_ref: Table = None

    @property
    def data_type(self) -> str:
        data_type_ref = self.table_ref.primary_key.data_type
        if "varchar" in data_type_ref:
            return data_type_ref
        else:
            return FK_TYPES.get(data_type_ref, 'bigint')

    @staticmethod
    def is_fk() -> bool:
        """Returns true if the column is a foreign key.

        Returns:
            bool: True if it is foreign key
        """
        return True

    # FIXME: Avoid overwritting the the repr method
    # NOTE: Overwrite dataclass method to show data_type property
    def __repr__(self):
        return f"FKColumn(name={self.name} data_type={self.data_type} table_ref.name={self.table_ref.name})"
