# Upload Storage Deduplication Plan

## Context

HaloWebUI stores uploaded file bodies under `DATA_DIR/uploads` and stores file
metadata in the `file` database table. The database keeps each upload's id,
owner, display filename, storage path, metadata, and access control. Large file
bodies should stay outside the database because binary blobs make SQLite and
backup workflows larger, slower, and harder to recover.

Current uploads receive a unique UUID-prefixed filename. If a user uploads the
same large file twice, both database rows are valid and both physical files are
stored independently. Later processing can produce the same content hash, but
that hash is not currently used to share the original upload body.

## Goals

- Prevent future duplicate upload bodies from consuming duplicate disk space.
- Preserve one database row per upload so chat history, user ownership,
  knowledge references, and permissions keep working.
- Keep each row's `path` valid even when multiple rows refer to identical file
  contents.
- Remediate existing duplicate files without changing database rows.
- Make remediation safe by default with a dry-run mode.

## Non-Goals

- Store large uploads in the SQL database.
- Deduplicate processed vector chunks. Vector storage is keyed by file and has
  separate lifecycle concerns.
- Change remote object-storage semantics in the first implementation.

## Upload-Time Deduplication Design

Add local-storage upload deduplication behind a feature flag:

- `ENABLE_UPLOAD_DEDUPE=true`
- `UPLOAD_DEDUPE_MIN_SIZE=1048576`
- `UPLOAD_DEDUPE_STRATEGY=hardlink`

The first implementation should support only local upload storage. S3, GCS, and
Azure can be added later with provider-specific object reuse and reference
counting.

### Upload Flow

1. Stream the incoming upload to a temporary file under `UPLOAD_DIR/.incoming`.
2. While streaming, calculate the original file body's SHA-256 and byte size.
3. Reject empty files as today.
4. Look for an existing local file row with matching `meta.storage_sha256` and
   `meta.storage_size`.
5. Verify the candidate file still exists and its actual size/hash still match.
6. If a valid candidate exists:
   - Create the new UUID-prefixed upload path.
   - Hardlink the candidate file to the new path.
   - Remove the temporary upload.
   - Insert a new `file` row for the new upload id and path.
7. If no valid candidate exists:
   - Move the temporary upload to the new UUID-prefixed path.
   - Insert a new `file` row.
8. Store upload-body metadata in `file.meta`:
   - `storage_sha256`
   - `storage_size`
   - `dedupe.strategy`
   - `dedupe.linked`
   - `dedupe.canonical_file_id` when linked
9. Continue document/RAG processing exactly as today. The existing `file.hash`
   field can remain the processed-content hash.

Do not use `file.hash` as the physical-file dedupe key. It can represent
processed text content and may differ from the original binary file hash.

### Deletion Semantics

The current local delete behavior can remain valid for hardlinks. Deleting one
upload path unlinks that directory entry. The shared bytes remain on disk while
at least one hardlink still exists. When the final hardlink is removed, the file
body is reclaimed by the filesystem.

Remote storage providers should not reuse this exact deletion model. They need
an object reference count or a reverse lookup before deleting a shared object.

### Failure Handling

- If hardlink creation fails with `EXDEV`, fall back to a normal independent
  file move/copy and log the fallback. This protects deployments where uploads
  move across filesystems.
- If a candidate row exists but the file is missing or hash verification fails,
  ignore that candidate and store the upload independently.
- If database insertion fails after a hardlink or move, remove the newly created
  upload path.

### Tests

Add tests for:

- Same user uploads the same file twice: two file rows, two paths, one physical
  inode when local hardlink dedupe is enabled.
- Different users upload the same file: permissions stay per row, storage is
  shared.
- Deleting one duplicate path leaves the other path readable.
- Dedupe disabled: current independent-file behavior remains unchanged.
- Candidate file missing or mismatched hash: upload falls back safely.

## Existing Upload Remediation

Use `scripts/dedupe-uploads-hardlinks.py` for existing local uploads.

The script:

- Reads the `file` table from `webui.db`.
- Maps container paths like `/app/backend/data/uploads/...` to the supplied host
  `--data-dir`.
- Only touches DB-tracked files under `uploads`.
- Groups files by actual byte size and actual SHA-256 of the file body.
- Keeps the earliest-created path in each group as canonical.
- Replaces other physical copies with hardlinks to the canonical path.
- Leaves database rows and paths unchanged.
- Runs as dry-run unless `--apply` is passed.

Recommended production workflow:

```bash
python3 scripts/dedupe-uploads-hardlinks.py \
  --data-dir /root/docker-compose/halowebui/data \
  --min-size 1M
```

Review the output. Then run:

```bash
python3 scripts/dedupe-uploads-hardlinks.py \
  --data-dir /root/docker-compose/halowebui/data \
  --min-size 1M \
  --apply
```

Operational precautions:

- Take a backup of `DATA_DIR` first.
- Avoid running while large uploads are actively in progress.
- Keep the app running only if a short maintenance window is not possible.
  The hardlink replacement is path-preserving, but a quiet window reduces race
  risk.

