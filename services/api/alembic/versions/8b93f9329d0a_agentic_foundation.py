"""agentic_foundation

Revision ID: 8b93f9329d0a
Revises: 7a82e8218c9f
Create Date: 2026-10-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b93f9329d0a'
down_revision: Union[str, Sequence[str], None] = '7a82e8218c9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to include Phase 3.4 Agent Events and Agent Runs tables."""
    # 1. agent_events
    op.create_table(
        'agent_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('source_timestamp', sa.DateTime(), nullable=False),
        sa.Column('received_at', sa.DateTime(), nullable=False),
        sa.Column('role_id', sa.String(length=100), nullable=True),
        sa.Column('student_id', sa.Integer(), nullable=True),
        sa.Column('previous_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('source_reliability', sa.String(length=50), nullable=False),
        sa.Column('evidence_reference', sa.String(length=500), nullable=True),
        sa.Column('processing_status', sa.String(length=50), nullable=False),
        sa.Column('is_simulated', sa.Boolean(), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "processing_status IN ('pending', 'processed', 'ignored', 'failed', 'requires_human_review')",
            name='ck_agent_event_processing_status',
        ),
        sa.CheckConstraint(
            "source_reliability IN ('verified_employer', 'trusted_internal', 'unverified_third_party', 'simulated_demo')",
            name='ck_agent_event_source_reliability',
        ),
        sa.ForeignKeyConstraint(['role_id'], ['roles.role_id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('agent_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agent_events_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_events_event_id'), ['event_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_agent_events_event_type'), ['event_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_events_processing_status'), ['processing_status'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_events_role_id'), ['role_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_events_student_id'), ['student_id'], unique=False)

    # 2. agent_runs
    op.create_table(
        'agent_runs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('mission_id', sa.Integer(), nullable=True),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('engine_used', sa.String(length=100), nullable=False),
        sa.Column('decision_category', sa.String(length=50), nullable=False),
        sa.Column('is_simulated', sa.Boolean(), nullable=False),
        sa.Column('relevant_evidence', sa.Text(), nullable=True),
        sa.Column('tools_invoked', sa.Text(), nullable=False),
        sa.Column('tool_io_log', sa.Text(), nullable=False),
        sa.Column('decision_explanation', sa.Text(), nullable=False),
        sa.Column('proposal_id', sa.Integer(), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "decision_category IN ('no_action', 'informational_notification', 'proposed_mission_adjustment', 'human_review_required')",
            name='ck_agent_run_decision_category',
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'failed')",
            name='ck_agent_run_status',
        ),
        sa.ForeignKeyConstraint(['event_id'], ['agent_events.event_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['mission_id'], ['career_missions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['proposal_id'], ['mission_change_proposals.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('agent_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agent_runs_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_runs_event_id'), ['event_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_runs_mission_id'), ['mission_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_runs_student_id'), ['student_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_runs_decision_category'), ['decision_category'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_runs_proposal_id'), ['proposal_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema to remove Phase 3.4 Agentic Foundation tables."""
    with op.batch_alter_table('agent_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agent_runs_proposal_id'))
        batch_op.drop_index(batch_op.f('ix_agent_runs_decision_category'))
        batch_op.drop_index(batch_op.f('ix_agent_runs_student_id'))
        batch_op.drop_index(batch_op.f('ix_agent_runs_mission_id'))
        batch_op.drop_index(batch_op.f('ix_agent_runs_event_id'))
        batch_op.drop_index(batch_op.f('ix_agent_runs_id'))
    op.drop_table('agent_runs')

    with op.batch_alter_table('agent_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agent_events_student_id'))
        batch_op.drop_index(batch_op.f('ix_agent_events_role_id'))
        batch_op.drop_index(batch_op.f('ix_agent_events_processing_status'))
        batch_op.drop_index(batch_op.f('ix_agent_events_event_type'))
        batch_op.drop_index(batch_op.f('ix_agent_events_event_id'))
        batch_op.drop_index(batch_op.f('ix_agent_events_id'))
    op.drop_table('agent_events')
