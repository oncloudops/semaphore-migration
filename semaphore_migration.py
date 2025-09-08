#!/usr/bin/env python3
import sqlite3
import json
import os
import glob
import re

class SemaphoreMigration:
    def __init__(self, db_path='database.sqlite', export_dir='export'):
        """Initialize the SemaphoreMigration tool"""
        self.db_path = db_path
        self.export_dir = export_dir
        self.schema = {}
        self.table_relationships = {}
        self.mappings = {}
        # Precompile regex pattern for efficiency
        self.dir_pattern = re.compile(r'([a-z_]+)(__[a-z_]+)?_([0-9]+)')
        
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
                cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}';")
                create_sql = cursor.fetchone()
                create_sql = create_sql[0] if create_sql else ""
                
                # Parse foreign key relationships
                cursor.execute(f"PRAGMA foreign_key_list({table});")
                foreign_keys = cursor.fetchall()
                
                # Parse indexes
                cursor.execute(f"SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='{table}';")
                indexes = cursor.fetchall()
                
                self.schema[table] = {
                    'columns': [],
                    'create_sql': create_sql,
                    'foreign_keys': [],
                    'indexes': []
                }
                
                # Process column information
                for col in columns:
                    self.schema[table]['columns'].append({
                        'name': col[1],
                        'type': col[2],
                        'not_null': bool(col[3]),
                        'default_value': col[4],
                        'primary_key': bool(col[5])
                    })
                
                # Process foreign keys
                for fk in foreign_keys:
                    self.schema[table]['foreign_keys'].append({
                        'id': fk[0],
                        'seq': fk[1],
                        'table': fk[2],
                        'from': fk[3],
                        'to': fk[4],
                        'on_update': fk[5],
                        'on_delete': fk[6]
                    })
                
                # Record table relationships
                if table not in self.table_relationships:
                    self.table_relationships[table] = []
                for fk in foreign_keys:
                    self.table_relationships[table].append({
                        'type': 'foreign_key',
                        'table': fk[2],
                        'column': fk[3],
                        'referenced_column': fk[4]
                    })
                
                # Process indexes
                for idx in indexes:
                    self.schema[table]['indexes'].append({
                        'name': idx[0],
                        'sql': idx[1]
                    })
            
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
            # Validate export directory exists
            if not os.path.exists(self.export_dir):
                raise FileNotFoundError(f"Export directory not found: {self.export_dir}")
                
            # Walk through all subdirectories and files in the export directory
            for root, dirs, files in os.walk(self.export_dir):
                # Process directories
                for dir_name in dirs:
                    # Handle directories in the format table_name_id or table__relationship_id
                    match = self.dir_pattern.match(dir_name)
                    if match:
                        base_table = match.group(1)
                        relationship = match.group(2) if match.group(2) else ''
                        entity_id = match.group(3)
                        
                        # Build full table name
                        full_table = base_table + relationship
                        
                        # Record mapping relationship
                        dir_path = os.path.join(root, dir_name)
                        
                        # Initialize list if table not in mappings
                        self.mappings.setdefault(full_table, [])
                        
                        # Process JSON files in the directory
                        json_files = glob.glob(os.path.join(dir_path, '*.json'))
                        for json_file in json_files:
                            self.mappings[full_table].append({
                                'file_path': json_file,
                                'entity_id': entity_id,
                                'file_id': os.path.basename(json_file).split('.')[0]
                            })
                
                # Process files directly in the export directory
                for file_name in files:
                    if file_name.endswith('.json') and root == self.export_dir:
                        # Process JSON files in the root directory
                        table_name = file_name.split('.')[0]
                        
                        # Initialize list if table not in mappings
                        self.mappings.setdefault(table_name, [])
                        self.mappings[table_name].append({
                            'file_path': os.path.join(root, file_name),
                            'file_id': table_name
                        })
            
            # Special handling for files in the migrations directory
            migrations_dir = os.path.join(self.export_dir, 'migrations')
            if os.path.exists(migrations_dir):
                migration_files = glob.glob(os.path.join(migrations_dir, '*.json'))
                
                # Initialize list if migrations not in mappings
                self.mappings.setdefault('migrations', [])
                for migration_file in migration_files:
                    self.mappings['migrations'].append({
                        'file_path': migration_file,
                        'version': os.path.basename(migration_file).split('.')[0]
                    })
            
            return self.mappings
        except Exception as e:
            print(f"Error analyzing export structure: {str(e)}")
            return self.mappings
    
    def generate_sql_from_json(self, table_name, json_data):
        """Generate SQL INSERT statements based on table structure and JSON data"""
        sql_statements = []
        
        # Validate table exists in schema
        if table_name not in self.schema:
            print(f"Warning: Table {table_name} is not in the schema")
            return sql_statements
        
        table_schema = self.schema[table_name]
        
        # Ensure json_data is in list format
        records = json_data if isinstance(json_data, list) else [json_data]
        
        for record in records:
            # Skip empty records
            if not record:
                continue
                
            # Filter out columns that exist in the table
            valid_columns = []
            valid_values = []
            
            for col in table_schema['columns']:
                col_name = col['name']
                if col_name in record:
                    valid_columns.append(col_name)
                    value = record[col_name]
                    
                    # Process values based on their type
                    if value is None:
                        valid_values.append('NULL')
                    elif isinstance(value, bool):
                        valid_values.append('1' if value else '0')
                    elif isinstance(value, (int, float)):
                        valid_values.append(str(value))
                    else:
                        # Handle string values, escape single quotes
                        value_str = str(value).replace("'", "''")
                        valid_values.append(f"'{value_str}'")
            
            # Generate INSERT statement if there are valid columns
            if valid_columns:
                columns_str = ', '.join(valid_columns)
                values_str = ', '.join(valid_values)
                sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({values_str});"
                sql_statements.append(sql)
        
        return sql_statements
    
    def process_all_data(self, output_file='migrated_data.sql'):
        """Process all exported data and generate complete SQL statements"""
        try:
            # Get schema and analyze export structure
            self.get_schema_json()
            self.analyze_export_structure()
            
            # Initialize variables for SQL generation
            all_sql_statements = []
            processed_tables = set()
            table_file_counts = {}
            
            # Process each table's data
            for table_name, file_mappings in self.mappings.items():
                # Skip migrations and session tables
                if table_name == 'migrations' or table_name == 'session':
                    continue
                    
                # Process each file mapping
                for file_info in file_mappings:
                    file_path = file_info['file_path']
                    try:
                        # Determine actual table name from directory structure
                        actual_table = self._determine_actual_table(file_path, table_name)
                        
                        # Skip if table doesn't exist in schema or is session table
                        if actual_table not in self.schema or actual_table == 'session':
                            continue
                        
                        # Safely load JSON data
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # Update file count for this table
                        table_file_counts[actual_table] = table_file_counts.get(actual_table, 0) + 1
                        
                        # Add table comment only once
                        if actual_table not in processed_tables:
                            all_sql_statements.append(f"-- SQL statements for table: {actual_table}")
                            processed_tables.add(actual_table)
                        
                        # Generate and add SQL statements
                        sql_statements = self.generate_sql_from_json(actual_table, data)
                        all_sql_statements.extend(sql_statements)
                        all_sql_statements.append('')  # Empty line separator
                        
                    except json.JSONDecodeError:
                        print(f"Error: Invalid JSON format in file {file_path}")
                    except FileNotFoundError:
                        print(f"Error: File not found - {file_path}")
                    except Exception as e:
                        print(f"Error processing file {file_path}: {str(e)}")
            
            # Write all SQL statements to output file
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(all_sql_statements))
                
            # Print processing summary
            self._print_processing_summary(table_file_counts, output_file)
            return output_file
            
        except Exception as e:
            print(f"Fatal error during data processing: {str(e)}")
            raise
    
    def _determine_actual_table(self, file_path, default_table):
        """Determine the actual table name based on directory structure"""
        # Check if file is in a directory with pattern like table_name__relationship_id
        match = re.match(r'([a-z_]+)(__[a-z_]+)?_([0-9]+)', os.path.basename(os.path.dirname(file_path)))
        if match:
            return match.group(1) + (match.group(2) if match.group(2) else '')
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
                    print(f"  - {fk['column']} references {fk['references']['table']}.{fk['references']['column']}")
        else:
            print("No foreign key relationships found.")
        
        print("-----------------------------------")
        return relationships
        
    def _extract_relationships(self):
        """Extract foreign key relationships from schema"""
        relationships = {}
        
        for table_name, table_info in self.schema.items():
            if 'foreign_keys' in table_info and table_info['foreign_keys']:
                relationships[table_name] = []
                for fk in table_info['foreign_keys']:
                    # Extract referenced table and column
                    ref_table = fk['table']
                    ref_column = fk['to']
                    relationships[table_name].append({
                        'column': fk['from'],
                        'references': {'table': ref_table, 'column': ref_column}
                    })
        
        return relationships

if __name__ == '__main__':
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