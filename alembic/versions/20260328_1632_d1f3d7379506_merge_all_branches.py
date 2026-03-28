"""merge_all_branches

Revision ID: d1f3d7379506
Revises: 004, 008_add_analytics_indexes, 008_add_onboarding_fields, 012_add_tipo_lead_e_dna
Create Date: 2026-03-28 16:32:54.162154-03:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd1f3d7379506'
down_revision: Union[str, None] = ('004', '008_add_analytics_indexes', '008_add_onboarding_fields', '012_add_tipo_lead_e_dna')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
