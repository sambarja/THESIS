-- ============================================================
-- MIGRATION: Replace email with username in users table
-- Run this in Supabase SQL Editor (Database → SQL Editor)
-- ============================================================

-- Step 1: Add username column
ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT;

-- Step 2: Populate username from email prefix for existing rows
-- e.g. "headadmin@gmail.com" → "headadmin"
UPDATE users
SET username = split_part(email, '@', 1)
WHERE username IS NULL;

-- Step 3: Make username unique and required
ALTER TABLE users ALTER COLUMN username SET NOT NULL;
ALTER TABLE users ADD CONSTRAINT users_username_unique UNIQUE (username);

-- Step 4: Update role CHECK constraint to match actual roles used
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
  CHECK (role IN ('head_admin', 'fleet_manager', 'manager', 'driver'));

-- Step 5: Remove email column
ALTER TABLE users DROP COLUMN IF EXISTS email;

-- Done. Verify:
-- SELECT id, full_name, username, role, is_active FROM users ORDER BY role, full_name;
