"""career_mission_system

Revision ID: 7a82e8218c9f
Revises: 6c39a1817b3d
Create Date: 2026-10-22 23:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a82e8218c9f'
down_revision: Union[str, Sequence[str], None] = '6c39a1817b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to include Phase 3.3 Career Mission tables."""
    # 1. career_missions
    op.create_table(
        'career_missions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('target_role_id', sa.String(length=100), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('weekly_hours', sa.Integer(), nullable=False),
        sa.Column('engine_metadata', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_role_id'], ['roles.role_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('career_missions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_career_missions_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_career_missions_student_id'), ['student_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_career_missions_target_role_id'), ['target_role_id'], unique=False)

    # 2. mission_versions
    op.create_table(
        'mission_versions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('mission_id', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('source_schema_version', sa.String(length=50), nullable=False),
        sa.Column('plan_snapshot', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.String(length=100), nullable=False),
        sa.Column('approved_by', sa.String(length=255), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('total_estimated_hours_min', sa.Integer(), nullable=False),
        sa.Column('total_estimated_hours_max', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['mission_id'], ['career_missions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('mission_id', 'version_number', name='uq_mission_version'),
    )
    with op.batch_alter_table('mission_versions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mission_versions_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mission_versions_mission_id'), ['mission_id'], unique=False)

    # 3. mission_tasks
    op.create_table(
        'mission_tasks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('version_id', sa.Integer(), nullable=False),
        sa.Column('stable_key', sa.String(length=100), nullable=False),
        sa.Column('stage_number', sa.Integer(), nullable=False),
        sa.Column('stage_title', sa.String(length=150), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.Column('skill_name', sa.String(length=100), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('current_level', sa.Integer(), nullable=False),
        sa.Column('target_level', sa.Integer(), nullable=False),
        sa.Column('level_delta', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('estimated_hours_min', sa.Integer(), nullable=False),
        sa.Column('estimated_hours_max', sa.Integer(), nullable=False),
        sa.Column('completion_criteria', sa.Text(), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('prerequisite_task_keys', sa.Text(), nullable=False),
        sa.Column('evidence_id', sa.Integer(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('completed_by', sa.String(length=255), nullable=True),
        sa.Column('override_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('not_started', 'in_progress', 'completed')", name='ck_task_status'),
        sa.ForeignKeyConstraint(['evidence_id'], ['evidence_items.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['version_id'], ['mission_versions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('mission_tasks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mission_tasks_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mission_tasks_version_id'), ['version_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mission_tasks_skill_id'), ['skill_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mission_tasks_stable_key'), ['stable_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_mission_tasks_evidence_id'), ['evidence_id'], unique=False)

    # 4. task_progress_events
    op.create_table(
        'task_progress_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('from_status', sa.String(length=50), nullable=False),
        sa.Column('to_status', sa.String(length=50), nullable=False),
        sa.Column('evidence_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('actor', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['evidence_id'], ['evidence_items.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['task_id'], ['mission_tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('task_progress_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_task_progress_events_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_progress_events_task_id'), ['task_id'], unique=False)

    # 5. mission_change_proposals
    op.create_table(
        'mission_change_proposals',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('mission_id', sa.Integer(), nullable=False),
        sa.Column('base_version_number', sa.Integer(), nullable=False),
        sa.Column('proposed_by', sa.String(length=100), nullable=False),
        sa.Column('proposal_title', sa.String(length=200), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('diff_summary', sa.Text(), nullable=False),
        sa.Column('proposed_plan_payload', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('student_decision_notes', sa.Text(), nullable=True),
        sa.Column('decided_by', sa.String(length=255), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name='ck_proposal_status'),
        sa.ForeignKeyConstraint(['mission_id'], ['career_missions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('mission_change_proposals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mission_change_proposals_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mission_change_proposals_mission_id'), ['mission_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('mission_change_proposals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mission_change_proposals_mission_id'))
        batch_op.drop_index(batch_op.f('ix_mission_change_proposals_id'))
    op.drop_table('mission_change_proposals')

    with op.batch_alter_table('task_progress_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_task_progress_events_task_id'))
        batch_op.drop_index(batch_op.f('ix_task_progress_events_id'))
    op.drop_table('task_progress_events')

    with op.batch_alter_table('mission_tasks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mission_tasks_evidence_id'))
        batch_op.drop_index(batch_op.f('ix_mission_tasks_stable_key'))
        batch_op.drop_index(batch_op.f('ix_mission_tasks_skill_id'))
        batch_op.drop_index(batch_op.f('ix_mission_tasks_version_id'))
        batch_op.drop_index(batch_op.f('ix_mission_tasks_id'))
    op.drop_table('mission_tasks')

    with op.batch_alter_table('mission_versions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mission_versions_mission_id'))
        batch_op.drop_index(batch_op.f('ix_mission_versions_id'))
    op.drop_table('mission_versions')

    with op.batch_alter_table('career_missions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_career_missions_target_role_id'))
        batch_op.drop_index(batch_op.f('ix_career_missions_student_id'))
        batch_op.drop_index(batch_op.f('ix_career_missions_id'))
    op.drop_table('career_missions')
