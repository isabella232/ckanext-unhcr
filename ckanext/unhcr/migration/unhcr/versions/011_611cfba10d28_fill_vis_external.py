"""
Fill the visible_external field for all data containers
When we define this required field, we didn't update all values
https://github.com/okfn/ckanext-unhcr/commit/735aba6115dc4f549fa26c2dbda8acf38c20b50a

Revision ID: 611cfba10d28
Revises: 295a1905e9a6
Create Date: 2022-06-03 14:17:16.513231

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '611cfba10d28'
down_revision = '295a1905e9a6'
branch_labels = None
depends_on = None


def upgrade():
    print("Ensure visible_external defined and False for data_containers")
    # update all data_containers to have a visible_external value
    op.execute(
        """
        UPDATE group_extra 
        SET value = 'false' 
        WHERE key = 'visible_external' 
        AND (value is NULL or value = '');
        """
    )
    # Create new extras for data_containers without any visible_external value.
    op.execute(
        """
        insert into group_extra ("id", "group_id", "key", "value", "state")
            select md5(random()::text || clock_timestamp()::text)::uuid,
                "group".id, 'visible_external', 'false', 'active' from "group"
                left join group_extra on
                    group_extra.group_id = "group".id 
                    and group_extra.key = 'visible_external'
                    and "group".type = 'data-container'
                where group_extra.key IS NULL;
      """
    )

def downgrade():
    pass
