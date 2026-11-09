ALTER TABLE media_channel_account_type
    DROP INDEX uk_media_account_type_code_deleted,
    DROP COLUMN account_type_code;
