-- Add missing columns to installations_airconunit table

-- Add labor_warranty_months (from migration 0022)
ALTER TABLE installations_airconunit 
ADD COLUMN IF NOT EXISTS labor_warranty_months INTEGER NULL;

-- Add is_deleted and deleted_at (from migration 0023)
ALTER TABLE installations_airconunit 
ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE installations_airconunit 
ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE NULL;

-- Add parts_warranty_months (from migration 0024)
ALTER TABLE installations_airconunit 
ADD COLUMN IF NOT EXISTS parts_warranty_months INTEGER NULL;

-- Add compressor_warranty_months to airconmodel (from migration 0025)
ALTER TABLE installations_airconmodel 
ADD COLUMN IF NOT EXISTS compressor_warranty_months INTEGER NOT NULL DEFAULT 60;

-- Verify columns were added
SELECT 
    column_name, 
    data_type, 
    is_nullable 
FROM information_schema.columns 
WHERE table_name = 'installations_airconunit' 
    AND column_name IN ('labor_warranty_months', 'is_deleted', 'deleted_at', 'parts_warranty_months', 'compressor_warranty_months')
ORDER BY column_name;

SELECT 
    column_name, 
    data_type, 
    is_nullable 
FROM information_schema.columns 
WHERE table_name = 'installations_airconmodel' 
    AND column_name IN ('compressor_warranty_months')
ORDER BY column_name;
