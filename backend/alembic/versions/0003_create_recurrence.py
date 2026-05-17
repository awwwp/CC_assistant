"""create recurrence_rules, task_instances, task_completion_log tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recurrence_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("rrule", sa.String(), nullable=False),
        sa.Column("dtstart", sa.Date(), nullable=False),
        sa.Column("dtend", sa.Date(), nullable=True),
        sa.Column("time_of_day", sa.Time(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("tag_id", sa.Integer(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "ix_recurrence_rules_series_id", "recurrence_rules", ["series_id"]
    )

    op.create_table(
        "task_instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("override_title", sa.String(), nullable=True),
        sa.Column("override_time", sa.Time(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["recurrence_rules.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "rule_id", "occurrence_date", name="uq_task_instances_rule_date"
        ),
    )
    op.create_index("ix_task_instances_rule_id", "task_instances", ["rule_id"])
    op.create_index(
        "ix_task_instances_occurrence_date",
        "task_instances",
        ["occurrence_date"],
    )

    op.create_table(
        "task_completion_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("title_snapshot", sa.String(), nullable=False),
        sa.Column("tag_color_snapshot", sa.String(), nullable=True),
        sa.Column("category_snapshot", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["recurrence_rules.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "ix_task_completion_log_rule_id", "task_completion_log", ["rule_id"]
    )
    op.create_index(
        "ix_task_completion_log_series_id",
        "task_completion_log",
        ["series_id"],
    )
    op.create_index(
        "ix_task_completion_log_occurrence_date",
        "task_completion_log",
        ["occurrence_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_task_completion_log_occurrence_date",
        table_name="task_completion_log",
    )
    op.drop_index(
        "ix_task_completion_log_series_id", table_name="task_completion_log"
    )
    op.drop_index(
        "ix_task_completion_log_rule_id", table_name="task_completion_log"
    )
    op.drop_table("task_completion_log")

    op.drop_index(
        "ix_task_instances_occurrence_date", table_name="task_instances"
    )
    op.drop_index("ix_task_instances_rule_id", table_name="task_instances")
    op.drop_table("task_instances")

    op.drop_index(
        "ix_recurrence_rules_series_id", table_name="recurrence_rules"
    )
    op.drop_table("recurrence_rules")
