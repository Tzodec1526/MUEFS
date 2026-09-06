# Private case archive export

The case export command creates a portable records-transfer package from a consistent
database snapshot and the corresponding stored files. It is intended for court IT and
records personnel with database and storage access. The archive includes nonpublic
material and personal information; use a destination approved for those records.

## Create and verify an archive

Run from the backend environment with its configured `DATABASE_URL` and document-storage
settings. The destination directory must already exist, and the output must be a new file.
The destination filesystem must support hard links, such as NTFS or ext4, so publishing
the completed archive cannot overwrite another export.

```sh
python -m app.case_export export --case-id 123 --output /court-transfer/case-123.zip
```

On success, the command prints one JSON result with `status: "exported"`, table counts
and `manifest_sha256`. Retain this result separately in the court's transfer record.
The command exits with zero on success and one on failure; failure diagnostics go to
standard error without connection credentials. It does not write an event to the source
database or change any stored file.

The recipient can check the archive without connecting to a database or object store:

```sh
python -m app.case_export verify /court-transfer/case-123.zip --manifest-sha256 RECORDED_SHA256
```

Replace `RECORDED_SHA256` with the fingerprint recorded by the exporting operator.
Verification checks the separately retained manifest fingerprint, every listed entry's
length and SHA-256, and the exact entry inventory. It rejects duplicate or unlisted entries
and unsafe archive paths. It never extracts or executes documents. Omitting the optional
fingerprint checks the archive's internal consistency only. A checksum is not a digital
signature or independent proof of court authenticity.

Before publishing an archive, export also validates document-delivery packets against
their original receipt, selected document manifests, retained selection fingerprint and
frozen recipient/notification links. Missing or inconsistent delivery evidence stops the
export before a completed archive is created. A cross-case receipt, contact or notification
reference blocks export of either affected case. Properly versioned later contact changes
and later filing submissions leave historical packets valid. These checks share the
[recovery audit](STORAGE_RECOVERY.md); they do not certify service or independently
authenticate the retained portal/SMTP activity.

## Included records

The archive contains the selected case and its court and case types, plus:

- Every envelope linked to the case, including pending, returned and rejected filings.
- Current and superseded original documents, private court orders, and all prepared public
  copies, including copies that are not currently published.
- Retained filing transactions, including their original document manifests and decisions.
- Participant records, private contact information, service-contact records and access flags.
- Allocated payments and legacy payment references, with recorded status and assessment basis.
- Filing notices, retained messages, and their delivery events.
- Selected document delivery packages, frozen recipient instructions and addresses, and
  recipient acknowledgments, download requests and retry requests. Linked notification
  events retain the corresponding email messages and relay outcomes.
- Court-reviewed delivery-failure reports, including their source references, observation
  times and linked sender attention notices. Source evidence referenced by a report is
  outside this archive unless separately retained among the case's documents.
- The court's published calendar revisions and audit events tied to the exported case,
  filings, documents, copies, payments and notifications.
- Limited profiles for referenced users, preserving attribution without exporting their
  identity-provider subjects or global identity/authorization administration.

Membership follows recorded case IDs. Unlinked drafts and other cases are outside the
export. Global configuration, court role assignments, identity-provider data, secrets,
legal-hold policy and records already absent from the source are outside this package.
It is not a database backup, automatic restore, certified court copy or migration adapter.
The receiving court must map source identifiers and validate access, retention, calendar,
financial and CMS records before importing them into another system.

## Format and integrity

The ZIP archive contains a plain-text `README.txt`, `manifest.json`, records in
`records/<table>.jsonl`, and document contents in `objects/<sha256>`.

Each JSONL line is a UTF-8 source record. Source IDs and relationships are preserved;
application timestamps are expressed in UTC and date-only fields remain dates. Monetary
fields retain their integer-cent representation. Document records include `object_path`
and their MIME type. Unsafe or private titles remain data inside the JSON records and
never become archive paths. Identical document contents share one archive object while
their source records remain separate.

The manifest records the format version, case and court IDs, source schema revision,
export times, table counts, and each entry's uncompressed size and SHA-256 fingerprint.
The manifest itself is covered by the fingerprint printed in the export result. Format
version 1 limits the manifest to 32 MiB; oversized exports fail explicitly.

The exporter reuses the recovery audit's retained-manifest checks before copying files.
Every distinct storage key is read and checked against its recorded hash and size, even
when another object with identical claimed contents was already exported. Missing,
modified or inconsistent evidence prevents publication of a completed archive. Failed
runs remove their temporary file. A forcibly terminated process can leave a hidden
`.case-export-*` temporary file; this is not a completed archive.

PostgreSQL uses a read-only repeatable-read transaction. SQLite is opened read-only with
an explicit read transaction, so a typo cannot create an empty source database. File
contents stream in 64 KiB chunks, metadata rows use batches of 250, and JSONL records are
written incrementally. The object index scales with the case's record count; referenced
users use database unions instead of a large list of query parameters.
Document entries use ZIP64 and are stored without recompression; JSON records are compressed.

## Verification evidence

`backend/tests/test_case_export.py` exercises SQLite and real PostgreSQL snapshots while
records change, complete private archives, superseded files, inactive public copies,
retained notices and payment bases, destination collisions, and altered archives. The
S3-compatible integration test verifies bounded reads, closed streams and corruption in
a second object whose original contents matched an already exported copy. Run the full
suite with the disposable PostgreSQL and S3 environment described in `STATE_READINESS.md`.
