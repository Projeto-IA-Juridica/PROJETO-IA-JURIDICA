"""merge_stripe_and_sessoes_branches

Revision ID: 272dee696f72
Revises: 016_add_stripe_fields, f6a7b8c9d0e1
Create Date: 2026-06-04 13:45:11.990858-03:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "272dee696f72"
down_revision: Union[str, None] = ("016_add_stripe_fields", "f6a7b8c9d0e1")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
