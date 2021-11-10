"""empty message

Revision ID: b57469f8882f
Revises: ccd38ad5fced
Create Date: 2021-11-05 17:17:53.299571

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b57469f8882f'
down_revision = '0a7c08639f19'
branch_labels = None
depends_on = None


def upgrade():
    """ Add the last_modified field for geographies """
    op.add_column(
        'geography',
        sa.Column(
            'last_modified',
            sa.DateTime,
            server_default=sa.func.current_timestamp(),
            onupdate=sa.func.current_timestamp()
        )
    )
    
def downgrade():
    op.drop_column('geography', 'last_modified')
