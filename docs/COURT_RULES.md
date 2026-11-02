# Court rules the code applies

These rules explain why the checklists, the validator and the seed data behave as they do.

## Which documents a filing needs

- **New case.** A new-case filing lists initiating pleadings only. Motion companions,
  responsive documents and proof or certificate of service are dropped, because service and
  its proof happen after the case is filed and the summons issued (MCR 2.104, MCR 2.107).
- **Subsequent filing or motion.** Only motion-related companions apply. The complaint and
  similar initiating documents are already on file. The validator enforces the companions
  on a subsequent filing only when it includes a motion, so an answer or other subsequent
  paper does not need them.
- **Any other filing type,** such as service-only: the requirements are returned unfiltered.
- **Requirements panel.** It uses the same document-code classifiers as the validator, so
  the UI shows exactly the set the validator enforces.
- **Motion documents.** Any motion document satisfies a motion-document requirement in both
  directions: a specific type (`MOT_SD`, `MOT_RECONSIDER`) covers a generic `MOTION` row, and
  the reverse.
- **`NOTICE_HEARING`** is the probate lists' spelling. The catalog uses `NOT_HEARING`.

## Motion companions

- **Brief.** MCR 2.119(A)(2) calls for a brief on motions raising a question of law, but the
  brief may be combined with the motion itself, so it is recommended and does not block.
- **Good-faith certification.** MCR 2.313(A) ties the meet-and-confer certification to
  discovery motions only (`MOT_COMPEL`, `MOT_PROTECTIVE`, `MOT_SANCTIONS`); other motions do
  not need it. A good-faith effort is a factor in awarding motion expenses (MCR 2.313(A)(5)),
  not a required filing, so `DISC_CERT_GF` is seeded and offered as recommended. Where a
  requirement row makes it required, the validator enforces that on discovery motions only.
- **Non-party motion to compel.** The catalog's help text says it must include the subpoena and
  proof of service (MCR 2.313(A)(2)(c)). The validator does not check for them, so a filing
  without them is not blocked.
- **Proposed order.** Not required at filing. MCR 2.602 governs entry of orders, so a proposed
  order is recommended practice, not a prerequisite.

## Filing dates

- **The filing date is the date filed.** It comes from the first receipt (MCR 1.109(G)(5)(b)).
  Acceptance never substitutes the acceptance time or a later receipt. It recomputes the civil
  date from the first receipt only when the published calendar changed. A correction never moves
  the date: a returned filing that is resubmitted gets a new numbered receipt and keeps its
  filing date.
- **Court orders.** A signed filing-date order sets the date, and a later resubmission keeps it.
  A court-ordered date is never recomputed.

## Seed data

- **One row per document.** Each court, case type and document code has one requirement row.
  Duplicates would render as duplicate checklist cards, so seeding fails loudly.
- **Motion requirements** attach alongside the initiating civil list. `EXHIBIT` and
  `PROOF_SERVICE` already come from that list and are not repeated. Affidavit and exhibit
  recommendations per motion type live in the catalog's companion rules.
- **Served, not filed.** Discovery papers served on parties rather than filed with the court
  (MCR 2.302(H)) never appear on a filing checklist.
- **Circuit civil checklist.** It stays limited to required and highly probable documents.
- **Small claims.** Circuit courts have general jurisdiction and take no small claims; those
  go to district courts, which have limited jurisdiction.
- **Court of Claims.** Statewide jurisdiction over claims against the State of Michigan,
  administratively part of the 30th Circuit Court in Ingham County (MCL 600.6401 et seq.).
- **Domesticating subpoena.** Uniform Interstate Depositions and Discovery Act, MCL 600.2201
  et seq.
- **Supreme Court application fee.** $375, the same as the Court of Appeals (MCL 600.321).

## Fees and case numbers

- **Fee examples.** The seeded amounts are visibly synthetic and never replace a court
  assessment. A subsequent filing is not necessarily a motion, so no $20 charge is assumed.
- **Case-number suffixes.** The demo catalog groups some subjects more broadly than SCAO's
  case types. The suffixes are representative classifications and do not replace a court's CMS
  assigning the official number. Without a connected CMS, acceptance records these numbers.
  Assigned numbers are never reformatted. Appellate entries use representative subject codes
  too; live appellate courts assign their own identifiers through their CMS. Source:
  [SCAO case type codes](https://courts.mi.gov/siteassets/court-administration/standardsguidelines/casefile/cf_casetypecodes.pdf).
