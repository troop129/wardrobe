"""add_ai_catalog_cutout_flag

Revision ID: d4e5f6a7b8c9
Revises: c1a2b3d4e5f6
Create Date: 2026-07-29

Tracks whether an item has had a successful OpenAI AI catalog cutout
(distinct from free rembg background removal).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c1a2b3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clothing_items",
        sa.Column(
            "ai_catalog_cutout",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Existing wardrobe already ran AI catalog cutout on every item with an image.
    op.execute(
        sa.text(
            "UPDATE clothing_items SET ai_catalog_cutout = true "
            "WHERE image_path IS NOT NULL"
        )
    )


def downgrade() -> None:
    op.drop_column("clothing_items", "ai_catalog_cutout")
