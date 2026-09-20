# Persistent raw data and approval pipeline

Released 20 September 2026. This stage connects the existing salon adapter, owner review screen and analytical engine to Supabase. It implements the agreed raw-to-clean workflow from the master handoff; it does not claim that the entire expanded metric catalogue has been implemented.

## Data flow

1. The password-protected Streamlit application stores the original UTF-8 CSV content as an immutable raw batch in `analyst_raw_batches` before cleaning.
2. The deterministic adapter normalises safe values and applies remembered owner decisions. Unresolved fields remain unavailable and the existing capability checks control analytical depth.
3. The owner reviews a new ambiguity and confirms a concrete correction. Proposals and discarded proposals do not publish anything.
4. One database transaction creates a cleaned version, records the approval, and moves the active dataset pointer. A concurrent change rejects a stale confirmation. Retries with the same event identifier are idempotent.
5. Ask your salon and Business evidence read that saved cleaned version. The analyst runs read-only queries and existing Python modules over that snapshot; GPT-4.1 mini interprets questions and explains verified evidence. Answer evidence includes the dataset version.
6. A new raw import reuses existing rules without another approval prompt. Import history links automatic applications to the original rule, approver and time.

The app reads `OPENAI_MODEL` from its existing secrets. This release preserves the configured model; the intended deployment setting is `gpt-4.1-mini`.

## Owner review and traceability

Data Validation contains the import control, unresolved issues, correction review, and approval/import history. The history shows original and approved values, scope, reason, approver and timestamp. Raw batches and cleaned versions retain full row lineage and cleaning audit details. The screen shows the latest 100 events and can export them; older records remain in Supabase.

Reusable staff aliases are scoped to their approved table and field and match case/whitespace variants. Record-specific cost or identity decisions are additionally bound to the original raw row fingerprint so changed source facts trigger fresh review. Manual sales remain distinct reviewed amendments; context never silently changes financial values. Checkpoint restoration appends reviewed decisions instead of erasing approval history.

Identity is still self-reported under the existing shared demo password. It is not individual Supabase Auth identity. This is a single-business B001 pilot, not a multi-tenant release.

## Supported imports

Upload the existing salon CSV structure as multiple files or one ZIP, at most 15 MB. Every import is a complete snapshot, including core business, staff, customer, item, booking, transaction and transaction-item tables. Optional module tables may be absent. Partial/incremental feeds and arbitrary source-system column mapping are subsequent adapter work. Unknown columns are rejected with a message rather than silently discarded.

The initial connection stores the current bundled fictional dataset once, applies existing safe rules, and leaves its three deliberately ambiguous issues unresolved. Later page loads read Supabase. A configured database outage stops the operation instead of silently reverting to bundled data. Without any Supabase configuration, the existing clearly labelled local preview remains available.

## Database deployment and recovery

`db/persistent_pipeline.sql` is the additive database upgrade applied to the hosted project. It uses invoker functions, server-role access, RLS, transaction locks and append-only history triggers. No new public read/write access is granted. The original dataset functions remain available.

The frozen GitHub baseline is `baseline-before-persistent-pipeline-20sep2026` at `bb066a3c4728836b5bdcc191120cfad95a5b9c8b`. Reverting application files to that baseline restores the previous app; it does not delete the newly stored database records. Historical clean versions and raw imports remain available for explicit recovery.

## Acceptance checks

Run `python -m pytest -q`. Tests cover existing analytical behaviour plus raw preservation, saved snapshot readback, scoped approval reuse, changed-source review, fresh-session persistence, duplicate import handling, rejection/discard, failed saves, and analyst evidence from a changed cleaned version. The controlled missing-sale test changes Sarah's net revenue from AUD 1,410 to AUD 1,510 while preserving original raw records; no live business sale is created by that test.

A rollback-only acceptance transaction was also run on the live Supabase project as `service_role`. It passed raw storage and readback, cleaned version publication, approval persistence, idempotent retry, stale-confirmation rejection, immutable raw history, rejection of erased approvals, rule reuse on a second raw batch and audit event linkage. Temporary test records were rolled back.

Supabase security advisors reported only informational notices that RLS tables have no client policies. This is intentional for server-role-only access in this pilot; anonymous and authenticated client roles have no table access. See the [Supabase RLS advisor description](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy).
