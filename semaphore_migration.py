#!/usr/bin/env python3
import sqlite3
import json
import os
import glob
import re


class SemaphoreMigration:
    def __init__(self, db_path="database.sqlite", export_dir="export"):
        """Initialize the SemaphoreMigration tool"""
        self.db_path = db_path
        self.export_dir = export_dir
        self.schema = {}
        self.table_relationships = {}
        self.mappings = {}
        self.autoincrement_tables = {}
        # Directory name to table name mapping for special cases
        self.directory_table_mapping = {"events": "event"}
        # Precompile regex pattern for efficiency
        self.dir_pattern = re.compile(r"([a-z_]+)(__[a-z_]+)?_([0-9]+)")
        # ID mapping dictionary to handle ID isolation between projects
        self.id_mappings = {}
        # Table processing order based on dependencies
        self.processing_order = []
        # Valid project IDs that exist in the project table
        self.valid_project_ids = set()

    def get_autoincrement_tables(self):
        """Get all tables with autoincrement primary key from existing schema"""
        if self.autoincrement_tables:
            return self.autoincrement_tables

        # Ensure schema is loaded
        if not self.schema:
            self.get_schema_json()

        # Check each table in the schema for autoincrement primary key
        for table_name, table_info in self.schema.items():
            # Skip sqlite_sequence table
            if table_name == "sqlite_sequence":
                continue

            # Check if table creation SQL contains AUTOINCREMENT
            if (
                "create_sql" in table_info
                and table_info["create_sql"]
                and "AUTOINCREMENT" in table_info["create_sql"].upper()
            ):
                # Find the primary key column name
                for col in table_info["columns"]:
                    if col["primary_key"]:
                        self.autoincrement_tables[table_name] = col["name"]
                        break

        return self.autoincrement_tables

    def get_schema_json(self):
        """Get complete table structure information from SQLite database, return in JSON format"""
        conn = None
        cursor = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get all table names
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]

            # Get structure for each table
            for table in tables:
                # Get table structure
                cursor.execute(f"PRAGMA table_info({table});")
                columns = cursor.fetchall()

                # Get table creation statement
                cursor.execute(
                    f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}';"
                )
                create_sql = cursor.fetchone()
                create_sql = create_sql[0] if create_sql else ""

                # Parse foreign key relationships
                cursor.execute(f"PRAGMA foreign_key_list({table});")
                foreign_keys = cursor.fetchall()

                # Parse indexes
                cursor.execute(
                    f"SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='{table}';"
                )
                indexes = cursor.fetchall()

                self.schema[table] = {
                    "columns": [],
                    "create_sql": create_sql,
                    "foreign_keys": [],
                    "indexes": [],
                }

                # Process column information
                for col in columns:
                    self.schema[table]["columns"].append(
                        {
                            "name": col[1],
                            "type": col[2],
                            "not_null": bool(col[3]),
                            "default_value": col[4],
                            "primary_key": bool(col[5]),
                        }
                    )

                # Process foreign keys
                for fk in foreign_keys:
                    self.schema[table]["foreign_keys"].append(
                        {
                            "id": fk[0],
                            "seq": fk[1],
                            "table": fk[2],
                            "from": fk[3],
                            "to": fk[4],
                            "on_update": fk[5],
                            "on_delete": fk[6],
                        }
                    )

                # Record table relationships
                if table not in self.table_relationships:
                    self.table_relationships[table] = []
                for fk in foreign_keys:
                    self.table_relationships[table].append(
                        {
                            "type": "foreign_key",
                            "table": fk[2],
                            "column": fk[3],
                            "referenced_column": fk[4],
                        }
                    )

                # Process indexes
                for idx in indexes:
                    self.schema[table]["indexes"].append(
                        {"name": idx[0], "sql": idx[1]}
                    )

            return self.schema
        except sqlite3.Error as e:
            print(f"Database error: {str(e)}")
            return self.schema
        finally:
            # Close database connections
            if cursor:
                try:
                    cursor.close()
                except sqlite3.Error:
                    pass
            if conn:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass

    def analyze_export_structure(self):
        """Analyze the structure of the export directory to determine the mapping relationship between tables and files"""
        try:
            # Clear mappings to ensure we start fresh
            self.mappings = {}

            # Validate export directory exists
            if not os.path.exists(self.export_dir):
                raise FileNotFoundError(
                    f"Export directory not found: {self.export_dir}"
                )

            # Walk through all subdirectories and files in the export directory
            for root, dirs, files in os.walk(self.export_dir):
                # Process directories
                for dir_name in dirs:
                    # Skip the migrations directory as it gets special handling later
                    if dir_name == "migrations":
                        continue

                    dir_path = os.path.join(root, dir_name)

                    # Check if directory matches the standard format (table_name_id or table__relationship_id)
                    match = self.dir_pattern.match(dir_name)
                    if match:
                        base_table = match.group(1)
                        relationship = match.group(2) if match.group(2) else ""
                        entity_id = match.group(3)

                        # Build full table name
                        full_table = base_table + relationship

                        # Initialize list if table not in mappings
                        self.mappings.setdefault(full_table, [])

                        # Process JSON files in the directory
                        json_files = glob.glob(os.path.join(dir_path, "*.json"))
                        for json_file in json_files:
                            self.mappings[full_table].append(
                                {
                                    "file_path": json_file,
                                    "entity_id": entity_id,
                                    "file_id": os.path.basename(json_file).split(".")[
                                        0
                                    ],
                                }
                            )
                    else:
                        # Handle directories that don't match the standard format
                        # Check if directory name has a special mapping to a table name
                        table_name = self.directory_table_mapping.get(
                            dir_name, dir_name
                        )

                        # Initialize list if table not in mappings
                        self.mappings.setdefault(table_name, [])

                        # Process JSON files in the directory
                        json_files = glob.glob(os.path.join(dir_path, "*.json"))
                        for json_file in json_files:
                            self.mappings[table_name].append(
                                {
                                    "file_path": json_file,
                                    "file_id": os.path.basename(json_file).split(".")[
                                        0
                                    ],
                                }
                            )

                # Process files directly in the export directory
                for file_name in files:
                    if file_name.endswith(".json") and root == self.export_dir:
                        # Process JSON files in the root directory
                        table_name = file_name.split(".")[0]

                        # Initialize list if table not in mappings
                        self.mappings.setdefault(table_name, [])
                        self.mappings[table_name].append(
                            {
                                "file_path": os.path.join(root, file_name),
                                "file_id": table_name,
                            }
                        )
            return self.mappings
        except Exception as e:
            print(f"Error analyzing export structure: {str(e)}")
            return self.mappings

    def generate_sql_from_json(self, table_name, json_data, project_id=None):
        """Generate SQL INSERT statements based on table structure and JSON data, handling ID mappings"""
        sql_statements = []

        # Validate table exists in schema
        if table_name not in self.schema:
            print(f"Warning: Table {table_name} is not in the schema")
            return sql_statements

        table_schema = self.schema[table_name]

        # Get autoincrement tables information
        if not self.autoincrement_tables:
            self.get_autoincrement_tables()

        # Ensure json_data is in list format
        records = json_data if isinstance(json_data, list) else [json_data]

        for record in records:
            # Skip empty records
            if not record:
                continue

            # Special check for records that depend on project_id
            # If this record has a project_id and that project doesn't exist, skip it
            if "project_id" in record and record["project_id"] is not None:
                if (
                    table_name != "project"
                    and record["project_id"] not in self.valid_project_ids
                ):
                    print(
                        f"Skipping record in table {table_name} with non-existent project_id: {record['project_id']}"
                    )
                    continue

            # Check if it's an autoincrement table
            exclude_id = False
            white_list_tables = ["project", "user", "task", "project__template"]
            if (
                table_name in self.autoincrement_tables
                and "id" in record
                and table_name not in white_list_tables
            ):
                exclude_id = True

            # Create a copy of the record to modify
            processed_record = record.copy()

            # Update foreign key references using id_mappings
            self._update_foreign_keys(processed_record, table_name)

            # For project table, track valid project IDs
            if table_name == "project" and "id" in processed_record:
                self.valid_project_ids.add(processed_record["id"])

            # Filter out columns that exist in the table
            valid_columns = []
            valid_values = []

            for col in table_schema["columns"]:
                col_name = col["name"]
                # Skip id column if it's an autoincrement table and id is 0
                if exclude_id and col_name == "id":
                    continue

                if col_name in processed_record:
                    valid_columns.append(col_name)
                    value = processed_record[col_name]

                    # Process values based on their type
                    if value is None:
                        valid_values.append("NULL")
                    elif isinstance(value, bool):
                        valid_values.append("1" if value else "0")
                    elif isinstance(value, (int, float)):
                        valid_values.append(str(value))
                    elif isinstance(value, dict):
                        # Store dictionaries as JSON bytes
                        try:
                            json_bytes = json.dumps(value).encode("utf-8")
                            # For SQLite, use X'hex string' format for BLOBs
                            hex_str = "".join([f"{byte:02x}" for byte in json_bytes])
                            valid_values.append(f"X'{hex_str}'")
                        except Exception as e:
                            # Fallback to string representation if JSON serialization fails
                            value_str = str(value).replace("'", "''")
                            valid_values.append(f"'{value_str}'")
                    else:
                        # Handle string values, escape single quotes and remove newlines
                        value_str = str(value).replace("'", "''").replace("\n", " ")
                        valid_values.append(f"'{value_str}'")

            # Generate INSERT statement if there are valid columns
            if valid_columns:
                columns_str = ", ".join(valid_columns)
                values_str = ", ".join(valid_values)
                sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({values_str});"
                sql_statements.append(sql)

        return sql_statements

    def _update_foreign_keys(self, record, table_name):
        """Update foreign key references in the record using id_mappings"""
        # Get foreign keys for this table
        if table_name in self.schema and "foreign_keys" in self.schema[table_name]:
            for fk in self.schema[table_name]["foreign_keys"]:
                fk_column = fk["from"]
                ref_table = fk["table"]
                ref_column = fk["to"]

                # Check if the record has this foreign key column
                if fk_column in record and record[fk_column] is not None:
                    # If we have a mapping for this foreign key, update it
                    source_id = record[fk_column]
                    if (
                        ref_table in self.id_mappings
                        and source_id in self.id_mappings[ref_table]
                    ):
                        record[fk_column] = self.id_mappings[ref_table][source_id]

    def _determine_processing_order(self, tables_with_data):
        """Determine the order to process tables based on their dependencies"""
        # Reset processing order
        self.processing_order = []
        processed = set()

        # Start with tables that have no dependencies or are core tables
        core_tables = ["user", "project", "option"]

        # Add core tables first if they have data
        for table in core_tables:
            if table in tables_with_data and table not in processed:
                self.processing_order.append(table)
                processed.add(table)

        # Add remaining tables in an order that respects dependencies
        while len(processed) < len(tables_with_data):
            added = False
            for table in tables_with_data:
                if table not in processed:
                    # Check if all dependencies are processed
                    dependencies = self._get_table_dependencies(table)
                    if all(
                        dep in processed
                        for dep in dependencies
                        if dep in tables_with_data
                    ):
                        self.processing_order.append(table)
                        processed.add(table)
                        added = True
            # If no tables could be added, break to avoid infinite loop
            if not added:
                break

        # Add any remaining tables that couldn't be ordered
        for table in tables_with_data:
            if table not in processed:
                self.processing_order.append(table)
                processed.add(table)

        return self.processing_order

    def _get_table_dependencies(self, table_name):
        """Get all tables that this table depends on through foreign keys"""
        dependencies = set()
        if table_name in self.schema and "foreign_keys" in self.schema[table_name]:
            for fk in self.schema[table_name]["foreign_keys"]:
                dependencies.add(fk["table"])
        return dependencies

    def process_all_data(self, output_file="migrated_data.sql"):
        """Process all exported data and generate complete SQL statements with proper ID mapping"""
        try:
            # Get schema and analyze export structure
            self.get_schema_json()
            self.analyze_export_structure()

            # Initialize variables for SQL generation
            all_sql_statements = []
            processed_tables = set()
            table_file_counts = {}
            tables_with_data = set()

            # First pass: collect all tables that have data to process
            for table_name, file_mappings in self.mappings.items():
                # Skip migrations and session tables
                if table_name == "migrations" or table_name == "session":
                    continue

                for file_info in file_mappings:
                    file_path = file_info["file_path"]
                    try:
                        actual_table = self._determine_actual_table(
                            file_path, table_name
                        )
                        if actual_table in self.schema and actual_table != "session":
                            tables_with_data.add(actual_table)
                    except Exception:
                        # Just skip if there's any error in determining actual table
                        pass

            # Add DELETE statements for all tables with data and reset autoincrement
            if tables_with_data:
                all_sql_statements.append(
                    "-- Clear existing data from tables before migration"
                )
                all_sql_statements.append(
                    "-- Reset autoincrement sequences to start from 0"
                )

                # First delete all data from tables
                for table in sorted(tables_with_data):
                    all_sql_statements.append(f"DELETE FROM {table};")

                # Then reset the autoincrement counter for each table
                # This will reset the ID sequence to start from 0
                all_sql_statements.append("")
                all_sql_statements.append("-- Reset autoincrement sequences")
                for table in sorted(tables_with_data):
                    all_sql_statements.append(
                        f"DELETE FROM sqlite_sequence WHERE name='{table}';"
                    )
                all_sql_statements.append("")

            # Determine processing order based on table dependencies
            self._determine_processing_order(tables_with_data)

            # Initialize ID mappings for each table
            for table in tables_with_data:
                self.id_mappings[table] = {}

            # Reset valid project IDs set
            self.valid_project_ids = set()

            # Process each table's data in the determined order
            processed_records = set()

            # Special handling for event table: collect all events first, then sort by created
            event_records = []

            for table_name in self.processing_order:
                # Skip if table is not in mappings
                if table_name not in self.mappings:
                    continue

                file_mappings = self.mappings[table_name]

                # Add table comment only once
                if table_name not in processed_tables and table_name != "event":
                    all_sql_statements.append(
                        f"-- SQL statements for table: {table_name}"
                    )
                    processed_tables.add(table_name)

                # Process each file mapping
                for file_info in file_mappings:
                    file_path = file_info["file_path"]
                    try:
                        # Determine actual table name from directory structure
                        actual_table = self._determine_actual_table(
                            file_path, table_name
                        )

                        # Skip if table doesn't exist in schema or is session table
                        if actual_table not in self.schema or actual_table == "session":
                            continue

                        # Safely load JSON data
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)

                        # Update file count for this table
                        table_file_counts[actual_table] = (
                            table_file_counts.get(actual_table, 0) + 1
                        )

                        # Special handling for event table: collect all records first
                        if actual_table == "event":
                            # Ensure data is in list format
                            records = data if isinstance(data, list) else [data]
                            for record in records:
                                if record:
                                    # Store the original record for later sorting
                                    event_records.append(record.copy())
                        else:
                            # For other tables, process normally
                            # Generate and add SQL statements with deduplication
                            sql_statements = self.generate_sql_from_json(
                                actual_table, data, file_info.get("entity_id")
                            )

                            # Deduplicate SQL statements
                            for sql in sql_statements:
                                # Create a unique key for each record based on table and values
                                # This helps identify and skip duplicate records
                                record_key = f"{actual_table}:{sql}"
                                if record_key not in processed_records:
                                    all_sql_statements.append(sql)
                                    processed_records.add(record_key)

                    except json.JSONDecodeError:
                        print(f"Error: Invalid JSON format in file {file_path}")
                    except FileNotFoundError:
                        print(f"Error: File not found - {file_path}")
                    except Exception as e:
                        print(f"Error processing file {file_path}: {str(e)}")

            # Now process event table with sorted records
            if event_records:
                # Add comment for event table
                all_sql_statements.append("")
                all_sql_statements.append(
                    "-- SQL statements for table: event (sorted by created)"
                )

                # Sort event records by 'created' field
                event_records.sort(key=lambda x: x.get("created", ""))

                # Generate SQL statements for sorted event records
                sql_statements = self.generate_sql_from_json("event", event_records)

                # Deduplicate and add to all_sql_statements
                for sql in sql_statements:
                    record_key = f"event:{sql}"
                    if record_key not in processed_records:
                        all_sql_statements.append(sql)
                        processed_records.add(record_key)

            # Write all SQL statements to output file
            with open(output_file, "w", encoding="utf-8") as f:
                f.write("\n".join(all_sql_statements))

            # Print processing summary
            self._print_processing_summary(table_file_counts, output_file)
            return output_file

        except Exception as e:
            print(f"Fatal error during data processing: {str(e)}")
            raise

    def _determine_actual_table(self, file_path, default_table):
        """Determine the actual table name based on directory structure"""
        # Check if file is in a directory with pattern like table_name__relationship_id
        match = re.match(
            r"([a-z_]+)(__[a-z_]+)?_([0-9]+)",
            os.path.basename(os.path.dirname(file_path)),
        )
        if match:
            return match.group(1) + (match.group(2) if match.group(2) else "")
        return default_table

    def _print_processing_summary(self, table_file_counts, output_file):
        """Print summary of files processed and output file information"""
        print("\nFiles processed per table:")
        for table, count in sorted(table_file_counts.items()):
            print(f"{table}: {count} files")

        print(f"\nSQL statements have been generated to {output_file}")

    def get_relationships_summary(self):
        """Get database table relationships summary"""
        if not self.schema:
            self.get_schema_json()

        print("Database Table Relationships Summary:")
        print("-----------------------------------")

        # Extract foreign key relationships
        relationships = self._extract_relationships()

        # Print relationship summary
        if relationships:
            for table_name, fks in sorted(relationships.items()):
                print(f"Table: {table_name}")
                for fk in fks:
                    print(
                        f"  - {fk['column']} references {fk['references']['table']}.{fk['references']['column']}"
                    )
        else:
            print("No foreign key relationships found.")

        print("-----------------------------------")
        return relationships

    def _extract_relationships(self):
        """Extract foreign key relationships from schema"""
        relationships = {}

        for table_name, table_info in self.schema.items():
            if "foreign_keys" in table_info and table_info["foreign_keys"]:
                relationships[table_name] = []
                for fk in table_info["foreign_keys"]:
                    # Extract referenced table and column
                    ref_table = fk["table"]
                    ref_column = fk["to"]
                    relationships[table_name].append(
                        {
                            "column": fk["from"],
                            "references": {"table": ref_table, "column": ref_column},
                        }
                    )

        return relationships


if __name__ == "__main__":
    print("\n========== Semaphore Data Migration Tool ==========")
    print("This tool will migrate your Semaphore data to SQL format.")
    print("==================================================\n")

    try:
        # Initialize migration tool
        migration = SemaphoreMigration()

        # Get database schema and analyze export structure
        print("Step 1: Reading database schema...")
        migration.get_schema_json()

        print("Step 2: Analyzing export directory structure...")
        migration.analyze_export_structure()

        # Show relationships summary
        print("Step 3: Extracting table relationships...")
        migration.get_relationships_summary()

        # Process all data and generate SQL
        print("Step 4: Processing data and generating SQL...")
        output_file = migration.process_all_data()

        # Success message
        print("\n========== Migration Complete ==========")
        print(f"✅ Data migration successfully completed!")
        print(f"✅ SQL file has been saved to: {output_file}")
        print("========================================")

    except FileNotFoundError as e:
        print("\n❌ Error: Required file not found!")
        print(f"Details: {str(e)}")
    except json.JSONDecodeError:
        print("\n❌ Error: Invalid JSON format in one of the export files!")
    except sqlite3.Error as e:
        print("\n❌ Error: Database access error!")
        print(f"Details: {str(e)}")
    except Exception as e:
        print("\n❌ Error: Migration failed!")
        print(f"Details: {str(e)}")
