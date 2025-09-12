# SemaphoreUI Migration Tool

A Python tool for migrating SemaphoreUI data from BoltDB export format to SQLite-compatible SQL INSERT statements. This tool reads the structure of an existing SQLite database and generates properly formatted SQL statements to populate that database with data from BoltDB exports.

## Features

- Reads SQLite database schema to ensure accurate data mapping
- Converts BoltDB exported JSON data to SQL INSERT statements
- Handles table dependencies and foreign key relationships
- Preserves autoincrement behavior and properly manages ID mapping
- Organizes SQL statements with table-specific comments
- Skips migrations and session tables automatically
- Generates file processing statistics for each table
- Outputs clean, readable SQL with proper formatting
- Supports processing of both standard format directories (with double underscores) and simple directories
- Allows custom mapping of directory names to table names (useful for directories with plural/singular naming discrepancies)

## Requirements

- Python 3.6 or higher
- SQLite3 (included with Python standard library)
- No external dependencies required (uses standard library modules: sqlite3, json, os, glob, re)

## Usage

### Step 1: Export Semaphore Data from BoltDB

You can use the [bolt2json](https://github.com/oncloudops/bolt2json) tool to export data from Semaphore's BoltDB database to JSON files:

1. Install bolt2json:
   ```bash
   git clone https://github.com/oncloudops/bolt2json
   cd bolt2json
   go build -o bolt2json
   ```

2. Export data from your Semaphore BoltDB database:
   ```bash
   # Default usage (reads database.boltdb and exports to ./export)
   ./bolt2json
   
   # Or specify custom paths
   ./bolt2json -db /path/to/your/semaphore/database.boltdb -output /path/to/export/directory
   ```

   This will create an `export` directory with subdirectories for each BoltDB bucket, containing JSON files for each key-value pair.

### Step 2: Prepare the Target SQLite Database

Ensure you have the target SQLite database file (`database.sqlite` by default) available in the same location as the migration script. This database should already have the required table structure.

### Step 3: Run the Migration Script

1. Ensure the exported data is in the `export` directory in the same location as the migration script
2. Run the migration script with default settings:

```bash
python3 semaphore_migration.py
```

3. Or specify custom paths:

```bash
# Create an instance with custom paths
python3 -c "from semaphore_migration import SemaphoreMigration; migration = SemaphoreMigration(db_path='/path/to/database.sqlite', export_dir='/path/to/export'); migration.process_all_data(output_file='custom_output.sql')"
```

4. The tool will generate a file named `migrated_data.sql` (or your custom name) containing all the SQL INSERT statements

## Project Structure

```
├── semaphore_migration.py  # Main migration script
├── .gitignore              # Git ignore file
├── README.md               # Project documentation
├── schema.txt              # Sample database schema reference
├── export/                 # Directory containing BoltDB export data
└── migrated_data.sql       # Generated SQL output file (created after running the script)
```

The `export` directory should contain subdirectories for each table with JSON files representing the data records. These directories can be in either standard format (with double underscores like `project__environment_0000000001`) or simple format (like `access_key` or `events`).

The script works with an existing SQLite database file (default: `database.sqlite`) which should be present in the same directory as the script.

## How It Works

The SemaphoreMigration class performs the following steps:

1. **Reads Database Schema**: Connects to the SQLite database to retrieve complete table structure information, including columns, data types, primary keys, and foreign key relationships.
2. **Analyzes Export Structure**: Scans the `export` directory to discover all tables and their corresponding JSON files.
3. **Determines Processing Order**: Analyzes table dependencies and determines the optimal order to process tables to maintain referential integrity.
4. **Processes Data**: For each table in the determined order:
   - Reads JSON data files
   - Maps foreign key references using ID mappings
   - Processes special cases like autoincrement tables
   - Generates properly formatted SQL INSERT statements
5. **Handles Special Tables**: Special handling for certain tables (like event table which is sorted by creation time)
6. **Writes SQL Output**: Writes all generated SQL statements to the output file
7. **Generates Summary**: Outputs statistics showing the number of files processed per table

## SQL Output Format

The generated SQL file has the following format:

```sql
-- Clear existing data from tables before migration
-- Reset autoincrement sequences to start from 0
DELETE FROM table1;
DELETE FROM table2;
-- More DELETE statements...

-- Reset autoincrement sequences
DELETE FROM sqlite_sequence WHERE name='table1';
DELETE FROM sqlite_sequence WHERE name='table2';
-- More sqlite_sequence DELETE statements...

-- SQL statements for table: table_name
INSERT INTO table_name (column1, column2, ...) VALUES (value1, value2, ...);
-- More INSERT statements for the same table...

-- SQL statements for table: another_table
INSERT INTO another_table (column1, column2, ...) VALUES (value1, value2, ...);
-- More INSERT statements...

-- SQL statements for table: event (sorted by created)
INSERT INTO event (column1, column2, ...) VALUES (value1, value2, ...);
-- More INSERT statements for event table...
```

The SQL file first clears existing data from all tables that will be populated and resets autoincrement sequences. Then it includes INSERT statements for each table, properly ordered to maintain referential integrity.

## Class Reference

### SemaphoreMigration

The main class responsible for handling the migration process.

#### Constructor

```python
SemaphoreMigration(db_path="database.sqlite", export_dir="export")
```

- `db_path`: Path to the SQLite database file (default: "database.sqlite")
- `export_dir`: Path to the directory containing BoltDB export data (default: "export")

#### Main Methods

- `get_schema_json()`: Retrieves the complete table structure information from the SQLite database
- `analyze_export_structure()`: Analyzes the structure of the export directory to determine the mapping relationship between tables and files
- `generate_sql_from_json(table_name, json_data, project_id=None)`: Generates SQL INSERT statements based on table structure and JSON data
- `process_all_data(output_file="migrated_data.sql")`: Processes all exported data and generates complete SQL statements with proper ID mapping
- `get_relationships_summary()`: Gets a summary of database table relationships

## Notes

- The tool automatically skips the `migrations` and `session` tables
- For standard format directories with numeric suffixes (e.g., `project__template_0000000001`), it identifies the actual table name
- For simple directories (e.g., `access_key`), it uses the directory name as the table name
- Custom directory-to-table mapping is supported for cases like plural directory names mapping to singular table names (e.g., `events` to `event`)
- The generated SQL file does not include CREATE TABLE statements; you should ensure the target database schema already exists
- All strings in the SQL output are properly escaped to prevent SQL injection
- The tool processes tables in an order that respects foreign key dependencies to maintain data integrity
- Special tables like `event` are processed differently (sorted by creation time)

## Error Handling

The tool includes comprehensive error handling for common issues:

- Missing database file
- Invalid JSON format in export files
- Database access errors
- General exceptions during processing

When errors occur, descriptive messages are displayed to help diagnose and resolve the issues.

## Error Messages

Common error messages and their meanings:

- `Error: Required file not found!`: The database file or export directory is missing
- `Error: Invalid JSON format in one of the export files!`: One of the JSON files in the export directory has invalid syntax
- `Error: Database access error!`: There was an issue accessing or reading from the SQLite database
- `Warning: Table {table_name} is not in the schema`: A table referenced in the export files doesn't exist in the database schema
- `Skipping record in table {table_name} with non-existent project_id: {project_id}`: A record references a project ID that doesn't exist in the project table

## License

MIT License

## Acknowledgments

This tool is designed to assist with migrating data between different installations of Ansible Semaphore or for backup purposes.

It provides a convenient way to convert data from BoltDB exports to SQL format, making it easier to transfer data between Semaphore instances or to perform data analysis and manipulation using SQL tools.