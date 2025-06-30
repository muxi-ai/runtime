"""
Fix user formation isolation by adding composite unique constraints.

This migration fixes the issue where external_user_id_hash had a global unique
constraint, preventing the same external user ID from existing in different
formations. The fix adds composite unique constraints scoped by formation.
"""

from alembic import op


def upgrade():
    """Add composite unique constraints for proper formation isolation."""

    # First, drop the existing unique constraints on individual columns
    with op.batch_alter_table("users") as batch_op:
        # Drop unique constraints on external_user_id and external_user_id_hash
        batch_op.drop_constraint("users_external_user_id_key", type_="unique")
        batch_op.drop_constraint("users_external_user_id_hash_key", type_="unique")

        # Add composite unique constraints
        batch_op.create_unique_constraint(
            "uq_user_formation_external_id", ["external_user_id_hash", "formation_id_hash"]
        )
        batch_op.create_unique_constraint(
            "uq_user_formation_external_id_plain", ["external_user_id", "formation_id"]
        )


def downgrade():
    """Revert to single-column unique constraints."""

    with op.batch_alter_table("users") as batch_op:
        # Drop composite unique constraints
        batch_op.drop_constraint("uq_user_formation_external_id", type_="unique")
        batch_op.drop_constraint("uq_user_formation_external_id_plain", type_="unique")

        # Re-add unique constraints on individual columns
        batch_op.create_unique_constraint("users_external_user_id_key", ["external_user_id"])
        batch_op.create_unique_constraint(
            "users_external_user_id_hash_key", ["external_user_id_hash"]
        )
