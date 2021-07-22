"""Add Geography Models

Revision ID: 65d2d180530c
Revises: 058f761ed45f
Create Date: 2021-07-01 11:31:04.118909

"""
from alembic import op
import sqlalchemy as sa
from ckanext.unhcr.models import Geography


# revision identifiers, used by Alembic.
revision = '65d2d180530c'
down_revision = '058f761ed45f'
branch_labels = None
depends_on = None


def upgrade():
    Geography.__table__.create()


def downgrade():
    Geography.__table__.drop()
