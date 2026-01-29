"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the main usage data table
    op.create_table(
        'circleci_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.String(length=255), nullable=True),
        sa.Column('organization_name', sa.String(length=255), nullable=True),
        sa.Column('organization_created_date', sa.TIMESTAMP(), nullable=True),
        sa.Column('project_id', sa.String(length=255), nullable=True),
        sa.Column('project_name', sa.String(length=255), nullable=True),
        sa.Column('project_created_date', sa.TIMESTAMP(), nullable=True),
        sa.Column('last_build_finished_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('vcs_name', sa.String(length=100), nullable=True),
        sa.Column('vcs_url', sa.Text(), nullable=True),
        sa.Column('vcs_branch', sa.String(length=255), nullable=True),
        sa.Column('pipeline_id', sa.String(length=255), nullable=True),
        sa.Column('pipeline_created_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('pipeline_number', sa.Numeric(), nullable=True),
        sa.Column('is_unregistered_user', sa.Boolean(), nullable=True),
        sa.Column('pipeline_trigger_source', sa.String(length=100), nullable=True),
        sa.Column('pipeline_trigger_user_id', sa.String(length=255), nullable=True),
        sa.Column('workflow_id', sa.String(length=255), nullable=True),
        sa.Column('workflow_name', sa.String(length=255), nullable=True),
        sa.Column('workflow_first_job_queued_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('workflow_first_job_started_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('workflow_stopped_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('is_workflow_successful', sa.Boolean(), nullable=True),
        sa.Column('job_name', sa.String(length=255), nullable=True),
        sa.Column('job_run_number', sa.Numeric(), nullable=True),
        sa.Column('job_id', sa.String(length=255), nullable=True),
        sa.Column('job_run_date', sa.TIMESTAMP(), nullable=True),
        sa.Column('job_run_queued_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('job_run_started_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('job_run_stopped_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('job_build_status', sa.String(length=50), nullable=True),
        sa.Column('resource_class', sa.String(length=100), nullable=True),
        sa.Column('operating_system', sa.String(length=100), nullable=True),
        sa.Column('executor', sa.String(length=100), nullable=True),
        sa.Column('parallelism', sa.Integer(), nullable=True),
        sa.Column('job_run_seconds', sa.Numeric(), nullable=True),
        sa.Column('median_cpu_utilization_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('max_cpu_utilization_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('median_ram_utilization_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('max_ram_utilization_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('compute_credits', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('dlc_credits', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('user_credits', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('storage_credits', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('network_credits', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('lease_credits', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('lease_overage_credits', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('ipranges_credits', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('total_credits', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for better query performance
    op.create_index('idx_circleci_usage_organization_id', 'circleci_usage', ['organization_id'])
    op.create_index('idx_circleci_usage_project_id', 'circleci_usage', ['project_id'])
    op.create_index('idx_circleci_usage_pipeline_id', 'circleci_usage', ['pipeline_id'])
    op.create_index('idx_circleci_usage_workflow_id', 'circleci_usage', ['workflow_id'])
    op.create_index('idx_circleci_usage_job_name', 'circleci_usage', ['job_name'])
    op.create_index('idx_circleci_usage_job_build_status', 'circleci_usage', ['job_build_status'])
    op.create_index('idx_circleci_usage_resource_class', 'circleci_usage', ['resource_class'])
    op.create_index('idx_circleci_usage_executor', 'circleci_usage', ['executor'])
    op.create_index('idx_circleci_usage_pipeline_created_at', 'circleci_usage', ['pipeline_created_at'])
    op.create_index('idx_circleci_usage_job_run_started_at', 'circleci_usage', ['job_run_started_at'])
    op.create_index('idx_circleci_usage_total_credits', 'circleci_usage', ['total_credits'])
    
    # Create unique index on job_id for UPSERT support
    # Note: Application code filters out NULL job_ids before insertion
    op.create_index(
        'idx_circleci_usage_job_id_unique',
        'circleci_usage',
        ['job_id'],
        unique=True
    )
    
    # Create a view for job performance analysis
    op.execute("""
        CREATE OR REPLACE VIEW job_performance AS
        SELECT 
            job_name,
            resource_class,
            executor,
            COUNT(*) as job_count,
            AVG(job_run_seconds) as avg_duration_seconds,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY job_run_seconds) as median_duration_seconds,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY job_run_seconds) as p95_duration_seconds,
            AVG(median_cpu_utilization_pct) as avg_cpu_utilization,
            AVG(median_ram_utilization_pct) as avg_ram_utilization,
            SUM(total_credits) as total_credits_used,
            AVG(total_credits) as avg_credits_per_job,
            SUM(CASE WHEN job_build_status = 'success' THEN 1 ELSE 0 END) as successful_jobs,
            SUM(CASE WHEN job_build_status = 'failed' THEN 1 ELSE 0 END) as failed_jobs,
            ROUND(
                SUM(CASE WHEN job_build_status = 'success' THEN 1 ELSE 0 END)::DECIMAL / COUNT(*) * 100, 2
            ) as success_rate_pct
        FROM circleci_usage
        GROUP BY job_name, resource_class, executor
        ORDER BY total_credits_used DESC
    """)
    
    # Create a view for cost analysis
    op.execute("""
        CREATE OR REPLACE VIEW cost_analysis AS
        SELECT 
            organization_name,
            project_name,
            DATE_TRUNC('day', pipeline_created_at) as usage_date,
            resource_class,
            executor,
            COUNT(*) as job_count,
            SUM(total_credits) as total_credits,
            AVG(total_credits) as avg_credits_per_job,
            SUM(compute_credits) as total_compute_credits,
            SUM(dlc_credits) as total_dlc_credits,
            SUM(user_credits) as total_user_credits,
            SUM(storage_credits) as total_storage_credits,
            SUM(network_credits) as total_network_credits,
            SUM(lease_credits) as total_lease_credits
        FROM circleci_usage
        WHERE pipeline_created_at IS NOT NULL
        GROUP BY organization_name, project_name, DATE_TRUNC('day', pipeline_created_at), 
                 resource_class, executor
        ORDER BY usage_date DESC, total_credits DESC
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS cost_analysis")
    op.execute("DROP VIEW IF EXISTS job_performance")
    op.drop_index('idx_circleci_usage_job_id_unique', table_name='circleci_usage')
    op.drop_index('idx_circleci_usage_total_credits', table_name='circleci_usage')
    op.drop_index('idx_circleci_usage_job_run_started_at', table_name='circleci_usage')
    op.drop_index('idx_circleci_usage_pipeline_created_at', table_name='circleci_usage')
    op.drop_index('idx_circleci_usage_executor', table_name='circleci_usage')
    op.drop_index('idx_circleci_usage_resource_class', table_name='circleci_usage')
    op.drop_index('idx_circleci_usage_job_build_status', table_name='circleci_usage')
    op.drop_index('idx_circleci_usage_job_name', table_name='circleci_usage')
    op.drop_index('idx_circleci_usage_workflow_id', table_name='circleci_usage')
    op.drop_index('idx_circleci_usage_pipeline_id', table_name='circleci_usage')
    op.drop_index('idx_circleci_usage_project_id', table_name='circleci_usage')
    op.drop_index('idx_circleci_usage_organization_id', table_name='circleci_usage')
    op.drop_table('circleci_usage')
