from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4f8e2a91b0d"
down_revision: Union[str, None] = "baec3dbedabf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("filing_envelopes", sa.Column("cms_case_number", sa.String(length=100), nullable=True))
    op.add_column("filing_envelopes", sa.Column("cms_filing_id", sa.String(length=100), nullable=True))
    op.add_column("filing_envelopes", sa.Column("cms_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("filing_envelopes", "cms_error")
    op.drop_column("filing_envelopes", "cms_filing_id")
    op.drop_column("filing_envelopes", "cms_case_number")
