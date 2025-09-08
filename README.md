# Semaphore Migration Tool

A Python tool for migrating Ansible Semaphore data from BoltDB export format to SQLite-compatible SQL INSERT statements.

## Features

- Converts BoltDB exported JSON data to SQL INSERT statements
- Organizes SQL statements with table-specific comments
- Skips migrations and session tables automatically
- Generates file processing statistics for each table
- Preserves data relationships between tables
- Outputs clean, readable SQL with proper formatting

## Requirements

- Python 3.6 or higher
- No external dependencies required (uses standard library modules)

## Usage

1. Ensure you have your Semaphore data exported in the BoltDB format in the `export` directory
2. Run the migration script:

```bash
python3 semaphore_migration.py
```

3. The tool will generate a file named `migrated_data.sql` containing all the SQL INSERT statements

## Project Structure

```
├── semaphore_migration.py  # Main migration script
├── export/                 # Directory containing BoltDB export data
└── migrated_data.sql       # Generated SQL output file
```

The `export` directory should contain subdirectories for each table with JSON files representing the data records.

## How It Works

1. The tool first scans the `export` directory to discover all tables and their corresponding JSON files
2. It builds a schema of the database tables by analyzing the JSON data structure
3. It generates SQL INSERT statements for each record, properly formatting values based on their data types
4. It adds comments to the SQL file to clearly separate statements for different tables
5. After processing all data, it outputs statistics showing the number of files processed per table

## SQL Output Format

The generated SQL file has the following format:

```sql
-- SQL statements for table: table_name
INSERT INTO table_name (column1, column2, ...) VALUES (value1, value2, ...);
-- More INSERT statements for the same table...

-- SQL statements for table: another_table
INSERT INTO another_table (column1, column2, ...) VALUES (value1, value2, ...);
-- More INSERT statements...
```

## Notes

- The tool automatically skips the `migrations` and `session` tables as these are typically not needed for data migration
- It processes directory names with numeric suffixes (e.g., `project__template_0000000001`) to identify the actual table name
- The generated SQL file does not include CREATE TABLE statements; you should ensure the target database schema already exists
- All strings in the SQL output are properly escaped to prevent SQL injection

## License

MIT License

## Acknowledgments

This tool is designed to assist with migrating data between different installations of Ansible Semaphore or for backup purposes.