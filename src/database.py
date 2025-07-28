import os
import logging
from dotenv import load_dotenv

from google.cloud import bigquery
from google.oauth2 import service_account
import pandas as pd

load_dotenv()

GCP_KEY_PATH = os.getenv("GCP_KEY_PATH", "./gcpkey.json")
DATABASE_NAME = os.getenv("DATABASE_NAME", "creditRisk")

FIELDS_DESCR = {
    f"{DATABASE_NAME}.train": {
        "REF_DATE": "data de referência do registro",
        "TARGET": "alvo binário de inadimplência (1: Mau Pagador, i.e. atraso > 60 dias em 2 meses)",
        "VAR2": "sexo do indivíduo ('M' ou 'F')",
        "IDADE": "idade do indivíduo",
        "VAR4": "flag de óbito ('S' indica que o indivíduo faleceu e NULL que não)",
        "VAR5": "unidade federativa (UF / estado) brasileira",
        "VAR8": "classe social estimada (de A até E, onde A é a mais alta e E a mais baixa)",
    }
}


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


class BigQueryDatabase:
    """BigQuery Database configuration, setup and access"""

    def __init__(self, database_name):
        self.database_name = database_name

        self._client, self.project_id = self._create_client()
        self.tables = self._load_tables()
        self.schemas = self._generate_schemas()

    def _create_client(self):
        try:
            if not os.path.exists(GCP_KEY_PATH):
                raise FileNotFoundError(f"GCP key file not found in {GCP_KEY_PATH}")

            credentials = service_account.Credentials.from_service_account_file(
                GCP_KEY_PATH
            )
            project_id = credentials.project_id

            _client = bigquery.Client(credentials=credentials, project=project_id)

            logger.info(f"BigQuery client created for project: {project_id}")

        except Exception as e:
            logger.error(f"Failed to create BigQuery client: {e}")
            raise

        return _client, project_id

    def _load_tables(self) -> list:
        """Load and return table names"""
        try:
            dataset_ref = f"{self.project_id}.{self.database_name}"

            # List tables and extract only the table_id (name)
            tables_iterator = self._client.list_tables(dataset_ref)
            table_names = [
                f"{self.database_name}.{table.table_id}" for table in tables_iterator
            ]

            logger.info(f"Found {len(table_names)} tables: {table_names}")
            return table_names

        except Exception as e:
            logger.error(f"Failed to load tables: {e}")
            return []

    def _generate_schemas(self):
        """Generates and formats schemas for to provide context"""
        schemas = []
        for table_name in self.tables:
            full_table_name = f"{self.project_id}.{table_name}"
            table_reference = self._client.get_table(full_table_name)

            schema = [f"Schema for {table_name}:"]

            # if DESCR available for table, use only fields with descriptions
            if table_name in FIELDS_DESCR:
                for field in table_reference.schema:
                    field_name = field.name
                    if field_name in FIELDS_DESCR[table_name]:
                        description = FIELDS_DESCR[table_name][field_name]
                        schema.append(
                            f"Nome: {field_name}, Descrição: {description}, Tipo: {field.field_type}, Modo: {field.mode}"
                        )
            else:
                for field in table_reference.schema:
                    schema.append(
                        f"Nome: {field.name}, Tipo: {field.field_type}, Modo: {field.mode}"
                    )
            schema.append("")

            schemas += schema

        return "\n".join(schemas)

    def get_bq_client(self) -> bigquery.Client:
        """Get BigQuery client if necessary"""
        return self._client

    def get_tables(self) -> list:
        """Get list of table names"""
        return self.tables

    def get_schemas(self) -> str:
        """Get schemas for all tables"""
        return self.schemas

    def run_query(self, query: str) -> pd.DataFrame:
        """Run SQL query and return results"""
        try:
            job = self._client.query(query)
            return job.to_dataframe()

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise


# instantiate single global client
bigquery_db = BigQueryDatabase(DATABASE_NAME)

def get_instance() -> BigQueryDatabase:
    """Get the global BigQueryDatabase instance"""
    return bigquery_db
