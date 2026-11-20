-- WhatsApp account shown on linked numbers (filled from the provider when the number connects).
ALTER TABLE wa_connections ADD COLUMN account_name TEXT NOT NULL DEFAULT '';
ALTER TABLE wa_connections ADD COLUMN profile_picture TEXT NOT NULL DEFAULT '';
