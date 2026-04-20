-- Migration: Add isactive column to symbols table if missing
ALTER TABLE symbols ADD COLUMN isactive TINYINT(1) NOT NULL DEFAULT 1;