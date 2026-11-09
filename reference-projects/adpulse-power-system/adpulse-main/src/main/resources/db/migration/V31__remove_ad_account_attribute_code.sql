ALTER TABLE ad_account_attribute
    DROP INDEX uk_ad_account_attribute_code_deleted,
    DROP COLUMN account_attribute_code;
