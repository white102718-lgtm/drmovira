-- Add settlement fields to the project closure application schema.
SET NAMES utf8mb4;
START TRANSACTION;

SET @settlement_amount_label = CONVERT(0xE7BB93E7AE97E98791E9A29D USING utf8mb4);
SET @settlement_amount_placeholder = CONVERT(0xE8AFB7E8BE93E585A5E4BB98E6ACBEE98791E9A29D USING utf8mb4);
SET @currency_label = CONVERT(0xE5B881E7A78D USING utf8mb4);
SET @currency_usd = CONVERT(0x555344202D20E7BE8EE58583 USING utf8mb4);
SET @currency_cny = CONVERT(0x434E59202D20E4BABAE6B091E5B881 USING utf8mb4);
SET @currency_jpy = CONVERT(0x4A5059202D20E697A5E58583 USING utf8mb4);
SET @application_section_label = CONVERT(0xE794B3E8AFB7E4BFA1E681AF USING utf8mb4);
SET @application_section_help = CONVERT(0xE8AFB7E68C89E5BD93E5898DE5AEA1E689B9E7B1BBE59E8BE8A1A5E58585E5BF85E8A681E5AD97E6AEB5EFBC8CE68F90E4BAA4E5908EE5B086E99A8FE5AEA1E689B9E58D95E4B880E5B9B6E79599E79795E38082 USING utf8mb4);
SET @settlement_period_label = CONVERT(0xE7BB93E7AE97E591A8E69C9F USING utf8mb4);
SET @settlement_period_placeholder = CONVERT(0xE4BE8BE5A682EFBC9A323032362D30382D303120E887B320323032362D30382D3331 USING utf8mb4);
SET @closure_description_label = CONVERT(0xE7BB93E9A1B9E8AFB4E6988E USING utf8mb4);
SET @closure_description_placeholder = CONVERT(0xE8AFB7E5A1ABE58699E9A1B9E79BAEE4BAA4E4BB98E5AE8CE68890E68385E586B5E38081E7BB93E7AE97E4BE9DE68DAEE58F8AE5A487E6B3A8 USING utf8mb4);
SET @project_section_label = CONVERT(0xE7BB93E9A1B9E9A1B9E79BAEE4BFA1E681AF USING utf8mb4);
SET @project_label = CONVERT(0xE9A1B9E79BAE USING utf8mb4);
SET @project_placeholder = CONVERT(0xE8AFB7E98089E68BA9E99C80E8A681E7BB93E9A1B9E79A84E9A1B9E79BAE USING utf8mb4);

UPDATE media_approval_config
SET form_schema = JSON_ARRAY(
      JSON_OBJECT('key', 'sectionProject', 'label', @project_section_label,
                  'type', 'section', 'required', false, 'width', 'full'),
      JSON_OBJECT('key', 'projectId', 'label', @project_label, 'type', 'select',
                  'required', true, 'width', 'half', 'optionSource', 'projects',
                  'placeholder', @project_placeholder),
      JSON_OBJECT('key', 'settlementAmount', 'label', @settlement_amount_label,
                  'type', 'number', 'required', true, 'width', 'half',
                  'minValue', 0.01, 'placeholder', @settlement_amount_placeholder,
                  'validationRule', 'positive-money'),
      JSON_OBJECT('key', 'settlementCurrency', 'label', @currency_label,
                  'type', 'select', 'required', true, 'width', 'half',
                  'optionSource', 'custom',
                  'options', JSON_ARRAY(@currency_usd, @currency_cny, @currency_jpy),
                  'defaultValue', @currency_usd),
      JSON_OBJECT('key', 'sectionApplication', 'label', @application_section_label,
                  'type', 'section', 'required', false, 'width', 'full',
                  'helpText', @application_section_help),
      JSON_OBJECT('key', 'settlementPeriod', 'label', @settlement_period_label,
                  'type', 'text', 'required', true, 'width', 'half',
                  'placeholder', @settlement_period_placeholder),
      JSON_OBJECT('key', 'closureDescription', 'label', @closure_description_label,
                  'type', 'textarea', 'required', true, 'width', 'full',
                  'maxLength', 300, 'placeholder', @closure_description_placeholder)
    ),
    updated_at = CURRENT_TIMESTAMP(3)
WHERE asset_type = 'PROJECT_CLOSURE' AND deleted_at = 0;

COMMIT;
