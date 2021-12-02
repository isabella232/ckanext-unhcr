"""pcode as Primary Key

Revision ID: 392dac5349ff
Revises: 8b51d24d322f
Create Date: 2021-11-25 18:54:41.882018

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '392dac5349ff'
down_revision = '8b51d24d322f'
branch_labels = None
depends_on = None


def upgrade():
    # pcodes are not ready to be used as primary keys yet
    op.execute("TRUNCATE table geography")
    # old values (using globalid) are no longer available
    op.execute("delete from package_extra where key='geographies'")
    op.drop_column('geography', 'globalid')
    op.create_primary_key('pk_pcode', 'geography', ['pcode'])


def downgrade():
    """ Not available """
    pass
