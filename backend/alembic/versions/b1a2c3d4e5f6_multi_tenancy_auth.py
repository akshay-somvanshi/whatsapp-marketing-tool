"""multi-tenancy & auth

Adds organizations / users / memberships, and an organization_id tenant key on
contacts, campaigns, conversations, messages. Existing rows are backfilled into
a single default organization so the migration is non-destructive.

Revision ID: b1a2c3d4e5f6
Revises: efcef6a74e6b
Create Date: 2026-06-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b1a2c3d4e5f6"
down_revision: Union[str, None] = "efcef6a74e6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # ── New tables ────────────────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("whatsapp_phone_number_id", sa.Text(), nullable=True),
        sa.Column("whatsapp_api_token", sa.Text(), nullable=True),
        sa.Column("whatsapp_business_account_id", sa.Text(), nullable=True),
        sa.Column("ai_provider", sa.Text(), nullable=False, server_default="anthropic"),
        sa.Column("anthropic_api_key", sa.Text(), nullable=True),
        sa.Column("gemini_api_key", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        sa.UniqueConstraint("whatsapp_phone_number_id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.Enum("owner", "admin", "agent", name="membership_role"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_index("ix_memberships_organization_id", "memberships", ["organization_id"])

    # ── Default org for backfilling existing single-tenant data ────────────────
    op.execute(
        sa.text(
            "INSERT INTO organizations (id, name, slug, ai_provider, created_at) "
            "VALUES (CAST(:id AS uuid), 'Default Organization', 'default', 'anthropic', now())"
        ).bindparams(id=DEFAULT_ORG_ID)
    )

    # ── Add organization_id (nullable → backfill → NOT NULL) ───────────────────
    for table in ("contacts", "campaigns", "conversations", "messages"):
        op.add_column(table, sa.Column("organization_id", sa.UUID(), nullable=True))
        op.execute(
            sa.text(
                f"UPDATE {table} SET organization_id = CAST(:id AS uuid)"
            ).bindparams(id=DEFAULT_ORG_ID)
        )
        op.alter_column(table, "organization_id", nullable=False)
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
        op.create_foreign_key(
            f"fk_{table}_organization",
            table,
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # ── Swap contact natural key: phone → (organization_id, phone) ─────────────
    # Drop dependent FKs first, then the old unique key.
    op.drop_constraint("conversations_contact_phone_fkey", "conversations", type_="foreignkey")
    op.drop_constraint("messages_contact_phone_fkey", "messages", type_="foreignkey")
    op.drop_constraint("conversations_contact_phone_key", "conversations", type_="unique")
    op.drop_constraint("contacts_phone_key", "contacts", type_="unique")

    op.create_unique_constraint("uq_contact_org_phone", "contacts", ["organization_id", "phone"])
    op.create_unique_constraint(
        "uq_conversation_org_phone", "conversations", ["organization_id", "contact_phone"]
    )
    op.create_foreign_key(
        "fk_conversations_contact",
        "conversations",
        "contacts",
        ["organization_id", "contact_phone"],
        ["organization_id", "phone"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_messages_contact",
        "messages",
        "contacts",
        ["organization_id", "contact_phone"],
        ["organization_id", "phone"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_messages_contact", "messages", type_="foreignkey")
    op.drop_constraint("fk_conversations_contact", "conversations", type_="foreignkey")
    op.drop_constraint("uq_conversation_org_phone", "conversations", type_="unique")
    op.drop_constraint("uq_contact_org_phone", "contacts", type_="unique")

    op.create_unique_constraint("contacts_phone_key", "contacts", ["phone"])
    op.create_unique_constraint("conversations_contact_phone_key", "conversations", ["contact_phone"])
    op.create_foreign_key(
        "conversations_contact_phone_fkey",
        "conversations",
        "contacts",
        ["contact_phone"],
        ["phone"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "messages_contact_phone_fkey",
        "messages",
        "contacts",
        ["contact_phone"],
        ["phone"],
        ondelete="CASCADE",
    )

    for table in ("messages", "conversations", "campaigns", "contacts"):
        op.drop_constraint(f"fk_{table}_organization", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_organization_id", table_name=table)
        op.drop_column(table, "organization_id")

    op.drop_index("ix_memberships_organization_id", table_name="memberships")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("organizations")
    op.execute("DROP TYPE IF EXISTS membership_role")
