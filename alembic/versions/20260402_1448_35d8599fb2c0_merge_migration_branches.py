"""Merge migration branches

Revision ID: 35d8599fb2c0
Revises: 012_add_tipo_lead_e_dna, 015_add_token_quota
Create Date: 2026-04-02 14:48:45.629618-03:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "35d8599fb2c0"
down_revision: Union[str, None] = ("012_add_tipo_lead_e_dna", "015_add_token_quota")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
