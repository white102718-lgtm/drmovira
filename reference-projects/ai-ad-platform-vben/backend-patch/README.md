# AdPulse system server V8 patch

The backend source repository is not present in this workspace. This directory keeps the
reviewable source and Flyway migration used for the incremental test-server patch.

- `DynamicAssetFlowController`: `/asset-flow-v2` dynamic forms, ordered handler/approver
  nodes, immutable application snapshots, approval records and notifications.
- `V8__dynamic_asset_flow.sql`: compatible extension of the existing V7 asset tables and
  the default PERSONAL/BM/PIXEL/TG workflows.
- `V9__approval_config_application_catalog.sql`: stores the business category, migrates the
  four MPower forms and allows future approval entries to use generated internal keys.
- `V10__mpower_pixel_form_validation.sql`: adds MPower-compatible pixel and numeric-ID
  validation rules to the saved low-code schema.
- `V11__mpower_form_constraints.sql`: restores the exact legacy labels and text-length
  constraints for PERSONAL/BM/PIXEL/TG schemas.
- `V12__project_closure_approval.sql`: creates the project-closure approval configuration,
  its catalog entry, and the project selector backed by the project management read model.
- `V13__project_closure_application_fields.sql`: adds the project-closure settlement amount,
  currency, settlement period, and closure description fields.
- `V14__project_closure_settlement_period_date_range.sql`: renders the settlement period as a
  date-range field.

The patch is compiled against the currently deployed server JAR and inserted into a backed-up
copy of that JAR. It should be moved into the canonical `adpulse-power-system` repository when
that source checkout becomes available.
