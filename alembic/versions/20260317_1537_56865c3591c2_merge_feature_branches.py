"""merge_feature_branches

Revision ID: 56865c3591c2
Revises: 003_add_processo_state, 007_add_pgvector
Create Date: 2026-03-17 15:37:21.131359-03:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "56865c3591c2"
down_revision: Union[str, None] = ("003_add_processo_state", "007_add_pgvector")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
