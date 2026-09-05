"""Record fee waiver decisions independently of filing acceptance."""

import sqlalchemy as sa
from alembic import op

revision = "f38d104ac927"
down_revision = "e91c62d7a104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("filing_envelopes", sa.Column("fee_waiver_referred_at", sa.DateTime(timezone=True)))
    op.add_column("filing_envelopes", sa.Column("fee_waiver_decided_at", sa.DateTime(timezone=True)))
    op.add_column("filing_envelopes", sa.Column("fee_waiver_amount_due_cents", sa.Integer()))
    op.create_index("ix_filing_court_waiver", "filing_envelopes", [
        "court_id", "fee_waiver_requested", "fee_waiver_granted", "submitted_at",
    ])
    # Legacy booleans are preserved. A null decided_at distinguishes the earlier
    # automatic state from a recorded, signed waiver decision; do not invent orders.


def downgrade() -> None:
    raise RuntimeError(
        "This migration retains fee waiver decisions and cannot be downgraded automatically. "
        "Restore a verified pre-migration "
        "backup under the court's recovery procedure instead of dropping decision data."
    )
