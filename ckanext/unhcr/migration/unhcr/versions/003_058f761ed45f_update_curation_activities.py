"""Update Curation Activities

Revision ID: 058f761ed45f
Revises: 222e309d2220
Create Date: 2021-05-21 14:42:59.382651

"""
import json
from alembic import op


# revision identifiers, used by Alembic.
revision = '058f761ed45f'
down_revision = '222e309d2220'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(
        """
        SELECT *
        FROM activity
        WHERE activity_type='changed package'
        """
    ).fetchall()

    for row in rows:
        try:
            data = json.loads(row.data)
        except ValueError:
            continue

        if 'curation_activity' not in data:
            continue

        conn.execute(
            """
            UPDATE activity
            SET activity_type='changed curation state'
            WHERE id=%s
            """,
            row.id
        )


def downgrade():
    conn.execute(
        """
        UPDATE activity
        SET activity_type='changed package'
        WHERE activity_type='changed curation state'
        """
    )
