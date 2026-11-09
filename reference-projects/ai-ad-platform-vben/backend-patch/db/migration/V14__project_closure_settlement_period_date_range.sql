-- Use a date-range control for the project closure settlement period.
SET NAMES utf8mb4;
START TRANSACTION;

SET @settlement_period_placeholder = CONVERT(0xE8AFB7E98089E68BA9E7BB93E7AE97E591A8E69C9F USING utf8mb4);

UPDATE media_approval_config
SET form_schema = JSON_REPLACE(
      form_schema,
      '$[5].type', 'date-range',
      '$[5].placeholder', @settlement_period_placeholder
    ),
    updated_at = CURRENT_TIMESTAMP(3)
WHERE asset_type = 'PROJECT_CLOSURE'
  AND deleted_at = 0
  AND JSON_UNQUOTE(JSON_EXTRACT(form_schema, '$[5].key')) = 'settlementPeriod';

COMMIT;
