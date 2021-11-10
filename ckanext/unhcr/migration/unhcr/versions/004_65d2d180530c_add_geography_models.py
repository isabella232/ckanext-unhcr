"""Add Geography Models

Revision ID: 65d2d180530c
Revises: 058f761ed45f
Create Date: 2021-07-01 11:31:04.118909

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '65d2d180530c'
down_revision = '058f761ed45f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'geography',
        sa.Column('globalid', sa.UnicodeText, primary_key=True),
        sa.Column('pcode', sa.UnicodeText, nullable=False),
        sa.Column('iso3', sa.UnicodeText, nullable=False),
        sa.Column('gis_name', sa.UnicodeText, nullable=False),
        sa.Column('gis_status', sa.Enum('active', 'inactive', name='geography_gis_statuse_enum'), nullable=False),
        sa.Column('layer', sa.UnicodeText, nullable=False),
        sa.Column('hierarchy_pcode', sa.UnicodeText, nullable=False)
    )


def downgrade():
    op.drop_table('geography')
