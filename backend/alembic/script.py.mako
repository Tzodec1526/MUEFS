<%!
    def without_comments(block):
        lines = [line for line in (block or "").splitlines() if not line.lstrip().startswith("#")]
        return "\n".join(lines).strip() or "pass"
%>from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${without_comments(upgrades)}


def downgrade() -> None:
    ${without_comments(downgrades)}
