"""Geography secondary territory

Revision ID: 8b51d24d322f
Revises: b57469f8882f
Create Date: 2021-11-12 12:39:18.468965

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8b51d24d322f'
down_revision = 'b57469f8882f'
branch_labels = None
depends_on = None


def upgrade():
    """ Add the last_modified field for geographies """
    op.add_column(
        'geography',
        sa.Column(
            'secondary_territory',
            sa.Boolean(),
            server_default=sa.false(),
        )
    )
    
def downgrade():
    op.drop_column('geography', 'secondary_territory')
