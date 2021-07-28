"""Move "visibility" from package level to resources

Revision ID: 0a7c08639f19
Revises: 058f761ed45f
Create Date: 2021-06-08 16:12:37.968904

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0a7c08639f19'
down_revision = '65d2d180530c'
branch_labels = None
depends_on = None


def upgrade():
    """ Select all resources without visibility defined and copy it from package extras """
    conn = op.get_bind()
    rows = conn.execute(
        """
        SELECT r.id, pe.value as visibility
        FROM resource as r
        JOIN package p on r.package_id = p.id
        JOIN package_extra pe on pe.package_id = p.id and pe.key='visibility'
        """
    ).fetchall()

    for row in rows:
        conn.execute(
            """
            UPDATE resource
                SET extras = jsonb_set(cast(extras as jsonb), '{{visibility}}', '"{}"', true)
            WHERE id='{}'""".format(row.visibility, row.id)
        )


def downgrade():
    pass
