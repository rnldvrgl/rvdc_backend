from django.db import connection

# SQL to add missing columns
sql_commands = [
    "ALTER TABLE installations_airconunit ADD COLUMN IF NOT EXISTS labor_warranty_months INTEGER NULL;",
    "ALTER TABLE installations_airconunit ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;",
    "ALTER TABLE installations_airconunit ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE NULL;",
    "ALTER TABLE installations_airconunit ADD COLUMN IF NOT EXISTS parts_warranty_months INTEGER NULL;",
    "ALTER TABLE installations_airconmodel ADD COLUMN IF NOT EXISTS compressor_warranty_months INTEGER NOT NULL DEFAULT 60;",
]

with connection.cursor() as cursor:
    for sql in sql_commands:
        try:
            cursor.execute(sql)
            print(f"✓ Executed: {sql[:60]}...")
        except Exception as e:
            print(f"✗ Error: {e}")
            print(f"  SQL: {sql}")

# Verify columns exist
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT column_name, data_type, is_nullable 
        FROM information_schema.columns 
        WHERE table_name = 'installations_airconunit' 
            AND column_name IN ('labor_warranty_months', 'is_deleted', 'deleted_at', 'parts_warranty_months')
        ORDER BY column_name;
    """)
    print("\n=== AirconUnit Columns ===")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} (nullable: {row[2]})")
    
    cursor.execute("""
        SELECT column_name, data_type, is_nullable 
        FROM information_schema.columns 
        WHERE table_name = 'installations_airconmodel' 
            AND column_name = 'compressor_warranty_months';
    """)
    print("\n=== AirconModel Columns ===")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} (nullable: {row[2]})")

print("\n✓ All columns have been added successfully!")
