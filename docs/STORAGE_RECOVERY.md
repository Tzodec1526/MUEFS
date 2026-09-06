# Document storage lifecycle and recovery

## Discarded draft cleanup

Removing an attachment from a never-submitted draft commits its metadata removal, audit
entry and `storage_deletions` job in one database transaction. The request does not contact
object storage. A failed commit leaves both the document record and its bytes intact.
Removing a previously received attachment from a returned filing retains its bytes and
history; it does not create a deletion job.

Apply migration `e95b20d7a6f1` before running the new API and storage worker. Run
`python -m app.storage_cleanup` as a supervised process with the **same database and file
collection as the API**. Docker Compose includes `storage-worker` with shared database/S3
configuration. Standalone SQLite deployments must also share `LOCAL_STORAGE_PATH`.
The worker refuses isolated demo databases, whose seeded file references can be shared
across visitors. Do not run it on a restore being audited or on one isolated demo database.

The worker checks indexed references in both original documents and public copies before
deleting a queued key. PostgreSQL workers skip jobs locked by another worker; SQLite
serializes cleanup transactions. Storage errors and remaining references leave the job
pending, with retry delays from 30 seconds to one hour. A crash or failed database commit
after the storage operation leaves the job retryable. Completed jobs become
`purge_draft_document` audit entries and leave the queue. No queue age alone authorizes
deletion; the committed removal and absence of references are both required.

For an operator run, `python -m app.storage_cleanup --once` processes currently due jobs
and exits: 0 means that run encountered no deferred jobs, 1 means at least one job was
deferred. A job scheduled for later is not attempted, so exit 0 does not prove the queue
is empty. Monitor backlog count, oldest `queued_at`, `next_attempt_at`, `attempt_count`
and `last_error` in `storage_deletions`; investigate increasing age or repeated errors.
Downgrading this migration requires an empty queue. Preserve the matching queue when
backing up or restoring the database.

Cleanup handles only committed draft removals. It does not inventory orphan uploads,
delete received records, or remove backup copies. It calls S3 `DeleteObject` without a
version ID; a versioned bucket can retain older bytes behind a delete marker. A completed
job therefore records deletion of the current object key, not proof that all historical
versions were erased. Manage versions and backup retention through the court's storage
policy. See [AWS DeleteObject semantics](https://docs.aws.amazon.com/AmazonS3/latest/API/API_DeleteObject.html).

## Verify a restored filing collection

`python -m app.storage_audit` checks stored bytes and retained file references without
changing database records or objects. Run it against a **quiescent restored database and
its matching file collection**, using read-only credentials. Keep the report with the
restore exercise's backup identifiers, operator record and application revision.

The command checks:

- Every `filing_documents` row, including drafts, removed/retained attachments, private
  documents and signed fee-waiver decisions.
- Every prepared public copy, including unpublished, superseded and withdrawn copies.
- SHA-256 and actual byte count, reading each referenced file in 64 KiB chunks.
- Document ownership and fingerprints retained in submission, service-recording and
  fee-waiver decision manifests, plus public-copy publication snapshots. These checks
  catch missing document metadata and current hashes altered to conceal changed bytes.
- Each document-delivery packet's case, filing and original submission/service-recording
  receipt, including both sides of a damaged cross-case reference.
- The selected document manifests against that original receipt, plus the retained request
  fingerprint binding the selected document IDs and contact IDs/versions. Missing selections
  are discrepancies even when some documents or recipients remain.
- Frozen recipient identity/instructions and their participant, contact and notification
  links. When the contact still has the frozen version, its complete snapshot must match.
  Later reviewed contact versions, retired participation and later filing submissions do
  not invalidate the historical packet. Recipient rows whose packet is missing are reported.

Receipt and delivery comparisons use batched metadata lookups rather than downloading
files again. The command fetches at most 250 file rows at a time, 25 transaction rows per
page and 25 delivery packets per page, including their JSON manifests. It counts recipients
before loading them and rejects packets outside the sending contract's 1..100 recipients;
a packet page loads at most 2,500 recipient snapshots. Delivery validation does not fetch
email message bodies. It does not load ORM relationships or the complete collection into
memory. PostgreSQL uses a read-only repeatable-read transaction;
SQLite uses a read-only file connection and an explicit read transaction. The database
snapshot does not freeze external objects. Use a restored or otherwise quiescent collection
to avoid concurrent writes and long-lived snapshots on the live court database.

## Configure and run

Install the backend and use the schema version supported by that application revision.
Supply connection settings through the operator's protected environment configuration;
do not put passwords into command history or the report.

| Setting | Restored PostgreSQL/S3 collection | Restored SQLite/local collection |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg` URL for the restored database and a SELECT-only account | `sqlite+aiosqlite` URL for an existing database file |
| `S3_ENDPOINT_URL`, `S3_BUCKET_NAME` | Restored object store and bucket | Unused |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Credentials permitted to GET restored objects | Unused |
| `LOCAL_STORAGE_PATH` | Unused | Absolute root of the restored files, preserving their stored relative keys; defaults to `demo_uploads` |

The database account needs schema access and SELECT on the application tables. The object
account needs to read referenced objects, including applicable KMS permissions on AWS.
It does not need permission to write, delete or enumerate objects. A provider may report
an unreadable/missing object as access denied when the account cannot list the bucket;
that is reported as `unavailable`, not assumed to be a missing file. S3 access follows the
provider's [GetObject permissions](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/get_object.html).

From an installed backend environment:

```bash
python -m app.storage_audit --output recovery-report.jsonl
```

`--output` creates a new UTF-8 JSON Lines file and refuses to overwrite an existing report.
Omit it to stream the report to stdout. For a scoped exercise:

```bash
python -m app.storage_audit --court-id 3 --output court-3-recovery.jsonl
```

The court selection is an operator filter, not a replacement for database permissions.
A nonexistent court produces an incomplete audit. The command does not select a hosted
demo visitor's database automatically; point `DATABASE_URL` at the intended restored file.
Reading an absent local file or directory does not create it.

## Interpret the evidence

Each report starts with a run ID, report schema version, UTC start time and court scope.
Current reports use `schema_version: 2`; version 1 reports did not validate delivery packets.
File records identify the document/copy and its expected and observed fingerprint/size.
Receipt records identify the transaction and referenced document/copy. New `service_packet`
and `service_recipient` rows identify the retained links. A valid packet request fingerprint
is included as `selection_sha256`, and a frozen contact snapshot's fingerprint as
`contact_sha256`. Compare these with the pre-backup report as well as the IDs and counts.
Private titles, addresses, filenames, storage keys, database URLs, credentials and raw
provider error messages are omitted.
The identifiers and hashes can still relate to private cases; protect the report.

| Status | Meaning and response |
| --- | --- |
| `verified` | Stored bytes match that document/copy record. |
| `metadata_consistent` | The current metadata agrees with the retained transaction reference. This row does not represent another storage read. |
| `missing` | The storage provider reported the referenced object/file missing. Restore it from the approved backup. |
| `mismatch` | Actual bytes differ from the recorded hash or size. Investigate the backup/object version; do not replace the expected hash to make the result pass. |
| `unavailable` | A storage read failed, including denied access or transport failure. Resolve configuration/availability and rerun. |
| `invalid_reference` | A local storage key fails path validation. Investigate the database record. |
| `invalid_metadata` | The file record lacks a valid SHA-256 or byte count. Recover authoritative metadata; an invented fingerprint is not evidence. |
| `missing_metadata` | A retained receipt or delivery refers to an absent document, packet, participant, contact, account or notification record. Recover the matching database backup. |
| `receipt_mismatch` | Current ownership or fingerprints conflict with the retained transaction. Investigate both database and object recovery. |
| `invalid_manifest` | A required document manifest or recipient selection/snapshot is missing or malformed. Its retained history could not be established. |
| `delivery_mismatch` | A packet's original receipt, document/contact selections, frozen instructions or notification links disagree. Recover the corresponding records; do not recompute fingerprints to conceal the discrepancy. |

Exit **0** means the scan completed without reported discrepancies. Exit **1** means it
completed and found discrepancies. Exit **2** means it could not complete or write its
report. An interrupted process exits unsuccessfully and can leave a partial report.
Require both process exit status 0 and the final `summary` record with `complete: true`
and `exit_code: 0`; earlier verified rows do not establish that the rest of the scan finished.

Also compare the scope, all file/reference identifiers and fingerprints, and counts with
the pre-backup inventory or audit of the same quiescent collection. A zero-discrepancy
report alone cannot detect records and receipts both absent from the restored database.
An empty collection reports zero checked files; it does not prove that an expected court
collection was recovered. Confirm notices, payments, access history and other database
records through the separate restore procedure as well. Packet checks establish the listed
document and routing relationships; they do not validate every portal-activity detail or
SMTP exchange, authenticate a delivery-failure report's external source, or establish
legally sufficient service. An orphan with no surviving case/court link can only be
identified by a full-collection audit, not attributed by a scoped report.

The command does not repair data, delete unreferenced objects, scan malware, certify
redactions or legal filing dates, validate retention policy, or prove continuing storage
immutability. Investigate discrepancies under the court's recovery procedure. Preserve
earlier reports and rerun into a new report after recovery.

## Verified local exercise and ongoing tests

A synthetic exercise used an Alembic-migrated PostgreSQL database, `pg_dump` custom-format
backup, `pg_restore` into a separate database, and files copied into a separate S3-compatible
bucket. Seven original/archived/order/copy files and six retained transaction references
produced identical detailed source and restored reports. The database and storage audit
accounts were explicitly denied writes. Same-length corruption, metadata changed to match
the altered bytes, a missing withdrawn copy and denied storage reads all failed the audit.
Restoring the known backup data reproduced the original results. This local exercise does
not establish a court's recovery-time/recovery-point targets or validate a production
provider's configuration.

`backend/tests/test_storage_audit.py` covers local audit behavior, malformed or missing
manifests, confidentiality of reports, bounded paging, report preservation and configured
local storage, including paths with spaces/URI characters and concurrent database changes.
`backend/tests/test_service_recovery.py` covers damaged packet selections and destinations,
cross-case links, lost recipients, malformed snapshots, legitimate historical changes,
orphaned records, bounded queries and sanitized CLI failures. It exercises both SQLite and
PostgreSQL; set `MUEFS_TEST_POSTGRES_URL` for the isolated PostgreSQL cases.
`backend/tests/test_s3_storage.py` exercises concurrent transfers, multipart
objects and missing-object behavior against disposable local S3-compatible storage. Set
`MUEFS_TEST_S3_ENDPOINT`, `MUEFS_TEST_S3_ACCESS_KEY` and `MUEFS_TEST_S3_SECRET_KEY` to enable
those integration tests; they accept only loopback endpoints and create/delete uniquely
named test buckets. CI supplies both PostgreSQL and disposable S3-compatible storage.

The S3 client is reused within each process, following Boto3's
[client concurrency guidance](https://docs.aws.amazon.com/boto3/latest/guide/clients.html).
It uses its own SDK session, rather than constructing clients concurrently through the
shared default session. Restart application workers after changing storage configuration
or static credentials. Comparing seven small PDFs against commit `84e7ce0` measured a
median verification pass of 123.387 ms before reuse and 10.765 ms with reuse, over five
warmed local S3-compatible samples. This excludes process startup and is not production
latency or capacity evidence.
