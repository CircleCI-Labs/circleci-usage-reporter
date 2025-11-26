#!/usr/bin/env python3
"""
Unified CircleCI Analysis Script

This script runs different types of CircleCI usage analysis notebooks and converts them to HTML.

Usage:
    python run_analysis.py --type job [--project PROJECT_NAME] [--job JOB_NAME]
    python run_analysis.py --type project [--project PROJECT_NAME] 
    python run_analysis.py --type compute-credits
    python run_analysis.py --type resource [--project PROJECT_NAME]
"""

import argparse
import os
import sys
import subprocess
import json
import tempfile
from pathlib import Path
import pandas as pd


ANALYSIS_TYPES = {
    'job': {
        'notebook': 'job_analysis.ipynb',
        'output': 'job-analysis-report.html',
        'title': 'Job Analysis Report'
    },
    'project': {
        'notebook': 'project_analysis.ipynb', 
        'output': 'project-analysis-report.html',
        'title': 'Project Analysis Report'
    },
    'compute-credits': {
        'notebook': 'compute_credits_by_project.ipynb',
        'output': 'compute-credits-report.html',
        'title': 'Compute Credits Report'
    },
    'resource': {
        'notebook': 'resource_class_analysis.ipynb',
        'output': 'resource-utilization-report.html',
        'title': 'Resource Utilization Report'
    }
}


def setup_environment():
    """Set up the environment for notebook execution."""
    # Set matplotlib backend for headless environment
    os.environ["MPLBACKEND"] = "Agg"
    
    # Ensure output directory exists
    output_dir = Path("/tmp/reports")
    output_dir.mkdir(exist_ok=True)
    
    print(f"Working directory: {os.getcwd()}")
    print(f"Output directory: {output_dir}")
    
    return output_dir


def find_highest_credit_project(csv_path="/tmp/merged.csv"):
    """
    Analyze the merged CSV file to find the project with the highest credit usage.
    
    Returns:
        str: The name of the project with the highest credit usage, or default if error
    """
    try:
        print(f"Analyzing merged data file: {csv_path}")
        
        # Read the CSV file
        df = pd.read_csv(csv_path, escapechar="\\", na_values=["\\N"])
        
        print(f"Loaded {len(df)} rows of data")
        
        # Check if we have the required columns
        if 'PROJECT_NAME' not in df.columns:
            print("Warning: PROJECT_NAME column not found, using default")
            return "your-project"
            
        # Calculate credit usage per project
        # Try different credit column names that might exist
        credit_columns = ['TOTAL_CREDITS', 'COMPUTE_CREDITS', 'CREDITS']
        credit_col = None
        
        for col in credit_columns:
            if col in df.columns:
                credit_col = col
                break
                
        if credit_col is None:
            print("Warning: No credit columns found, using default project name")
            return "your-project"
            
        print(f"Using credit column: {credit_col}")
        
        # Group by project and sum credits
        project_credits = df.groupby('PROJECT_NAME')[credit_col].sum().sort_values(ascending=False)
        
        print("Top 5 projects by credit usage:")
        for i, (project, credits) in enumerate(project_credits.head().items()):
            print(f"  {i+1}. {project}: {credits:,.0f} credits")
            
        # Get the project with highest usage
        highest_project = project_credits.index[0]
        highest_credits = project_credits.iloc[0]
        
        print(f"\nSelected project for analysis: {highest_project} ({highest_credits:,.0f} credits)")
        
        return highest_project
        
    except Exception as e:
        print(f"Error analyzing data file: {e}")
        print("Using default project name")
        return "your-project"


def run_existing_notebook_with_params(analysis_type, project_name=None, individual_job_name=None, credit_cost=0.0006):
    """
    Run existing notebook with parameters set via environment variables.
    Falls back to creating a minimal notebook if the notebook doesn't exist.
    """
    notebook_mapping = {
        'job': 'job_analysis.ipynb',
        'project': 'project_analysis.ipynb',
        'compute-credits': 'compute_credits_by_project.ipynb',
        'resource': 'resource_class_analysis.ipynb'
    }
    
    notebook_file = notebook_mapping.get(analysis_type)
    
    # Look for notebook in src directory (relative to script location)
    script_dir = Path(__file__).parent
    notebook_path = script_dir / notebook_file
    
    if notebook_file and notebook_path.exists():
        print(f"Using existing notebook: {notebook_path}")
        
        # Set environment variables for the notebook
        env_vars = {
            'FILEPATH': '/tmp/merged.csv',
            'CREDIT_COST': str(credit_cost)
        }
        
        if project_name:
            env_vars['PROJECT_NAME'] = project_name
        if individual_job_name:
            env_vars['JOB_NAME'] = individual_job_name
            
        # Update environment
        for key, value in env_vars.items():
            os.environ[key] = value
            
        print(f"Set environment variables: {env_vars}")
        return str(notebook_path)
    else:
        if notebook_file:
            print(f"Notebook not found at: {notebook_path}")
        print("Creating minimal notebook from scratch")
        return create_minimal_notebook(analysis_type, project_name, individual_job_name, credit_cost)


def create_minimal_notebook(analysis_type, project_name=None, individual_job_name=None, credit_cost=0.0006):
    """
    Create a minimal notebook that uses the common analysis library.
    This replaces the need for complex parameter injection.
    """
    
    # Create notebook content based on analysis type
    if analysis_type == 'job':
        cells = create_job_analysis_cells(project_name, individual_job_name, credit_cost)
    elif analysis_type == 'project':
        cells = create_project_analysis_cells(project_name, credit_cost)
    elif analysis_type == 'compute-credits':
        cells = create_compute_credits_cells(credit_cost)
    elif analysis_type == 'resource':
        cells = create_resource_analysis_cells(project_name, credit_cost)
    else:
        raise ValueError(f"Unknown analysis type: {analysis_type}")
    
    # Create notebook structure
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            },
            "language_info": {
                "name": "python",
                "version": "3.8.0"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 4
    }
    
    # Write to temporary file
    temp_notebook = tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False, dir=".")
    json.dump(notebook, temp_notebook, indent=2)
    temp_notebook.close()
    
    print(f"Created minimal notebook: {temp_notebook.name}")
    return temp_notebook.name


def create_base_setup_cells(org_name=None, report_name="Usage", project_name=None):
    """Create common setup cells used by all analysis types."""
    # Build the title with organization and project information
    title = f"# CircleCI {report_name} Analysis"
    
    # Add organization and project info as a subheader
    subtitle_parts = []
    if org_name:
        subtitle_parts.append(f"## Organization: {org_name}")
    if project_name:
        subtitle_parts.append(f"## Project: {project_name}")
    
    if subtitle_parts:
        subtitle = f"\n{chr(10).join(subtitle_parts)}"
        title += subtitle
    
    return [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [title + "\n\nGenerated analysis report using the unified analysis framework."]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# Import analysis library and initialize environment\n",
                "import analysis\n",
                "import pandas as pd\n",
                "import matplotlib.pyplot as plt\n",
                "\n",
                "# Initialize notebook environment\n", 
                "helpers = analysis.initialize_notebook()\n",
                "pp = helpers['pp']\n",
                "summarize_dataset = helpers['summarize_dataset']\n"
            ]
        }
    ]


def create_job_analysis_cells(project_name, individual_job_name, credit_cost):
    """Create cells for job analysis notebook."""
    import os
    org_name = os.getenv("CIRCLE_PROJECT_USERNAME", "unknown-org")
    cells = create_base_setup_cells(org_name=org_name, report_name="Job", project_name=project_name)
    
    cells.extend([
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Load and process data\n",
                f"df, project_dfs = analysis.load_circleci_data(\n",
                f"    filepath='/tmp/merged.csv',\n",
                f"    project_name='{project_name}',\n",
                f"    credit_cost={credit_cost}\n",
                f")\n",
                f"\n",
                f"# Extract datasets\n",
                f"all_jobs = project_dfs['all_jobs']\n",
                f"ps_jobs = project_dfs['ps_jobs']\n",
                f"ps_master_jobs = project_dfs['ps_master_jobs']\n",
                f"ps_pr_jobs = project_dfs['ps_pr_jobs']\n",
                f"\n",
                f"print('Dataset summaries:')\n",
                f"print(summarize_dataset(all_jobs, 'All jobs'))\n",
                f"print(summarize_dataset(ps_jobs, 'Project-specific jobs'))\n",
                f"print(summarize_dataset(ps_master_jobs, 'Master branch jobs'))\n",
                f"print(summarize_dataset(ps_pr_jobs, 'PR branch jobs'))\n"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Individual Job Analysis"]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Most expensive individual jobs\n",
                f"expensive_jobs = ps_jobs.sort_values('COST', ascending=False)\n",
                f"pp(expensive_jobs[['JOB_NAME', 'JOB_RUN_DATE', 'VCS_BRANCH', 'COST', 'DURATION', 'COMPUTE_CREDITS', 'JOB_URL']].head(), 'Most Expensive Individual Jobs')\n"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Slowest individual jobs\n",
                f"slow_jobs = ps_jobs.sort_values('JOB_RUN_SECONDS', ascending=False)\n",
                f"pp(slow_jobs[['JOB_ID', 'JOB_NAME', 'JOB_RUN_DATE', 'VCS_BRANCH', 'COST', 'DURATION', 'JOB_URL']].head(), 'Slowest Individual Jobs')\n"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Pipeline Analysis"]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Pipeline cost distribution\n",
                f"pr_pipeline_costs = ps_pr_jobs.groupby('PIPELINE_ID').agg(COST=('COST', 'sum')).reset_index()\n",
                f"analysis.plot_cost_distribution(\n",
                f"    pr_pipeline_costs['COST'],\n",
                f"    title='Pipeline cost distribution for PR branches',\n",
                f"    bins=60\n",
                f")\n"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Specific Job Analysis"]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Analysis of specific job: {individual_job_name}\n",
                f"individual_job_name = '{individual_job_name}'\n",
                f"filtered_jobs = ps_jobs[ps_jobs['JOB_NAME'] == individual_job_name]\n",
                f"\n",
                f"if filtered_jobs.empty:\n",
                f"    available_jobs = ps_jobs['JOB_NAME'].dropna().unique()[:5]\n",
                f"    print(f'⚠️  No data found for job \\'{individual_job_name}\\'. Available jobs: {{list(available_jobs)}}')\n",
                f"else:\n",
                f"    print(f'Found {{len(filtered_jobs)}} instances of job \\'{individual_job_name}\\'')\n",
                f"    analysis.analyse_durations(\n",
                f"        filtered_jobs['JOB_RUN_SECONDS'],\n",
                f"        title=f'Duration distribution for {{individual_job_name}}',\n",
                f"        max_xvalue=30*60,\n",
                f"        bins=20\n",
                f"    )\n"
            ]
        }
    ])
    
    return cells


def create_project_analysis_cells(project_name, credit_cost):
    """Create cells for project analysis notebook."""
    import os
    org_name = os.getenv("CIRCLE_PROJECT_USERNAME", "unknown-org")
    cells = create_base_setup_cells(org_name=org_name, report_name="Project", project_name=project_name)
    
    cells.extend([
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Load and process data\n",
                f"df, project_dfs = analysis.load_circleci_data(\n",
                f"    filepath='/tmp/merged.csv',\n",
                f"    project_name='{project_name}',\n",
                f"    credit_cost={credit_cost}\n",
                f")\n",
                f"\n",
                f"# Extract datasets\n",
                f"ps_jobs = project_dfs['ps_jobs']\n",
                f"ps_master_jobs = project_dfs['ps_master_jobs']\n",
                f"ps_pr_jobs = project_dfs['ps_pr_jobs']\n"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Aggregate Job Analysis"]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Aggregate analysis for master branch jobs\n",
                f"ps_master_jobs_aggregated = analysis.group_by_job_name(ps_master_jobs)\n",
                f"analysis.analyse_jobs(ps_master_jobs_aggregated, title_prefix='Master-branch jobs')\n"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Aggregate analysis for PR branch jobs\n",
                f"ps_pr_jobs_aggregated = analysis.group_by_job_name(ps_pr_jobs)\n",
                f"analysis.analyse_jobs(ps_pr_jobs_aggregated, title_prefix='PR-branch jobs')\n"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Pipeline and Workflow Analysis"]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Pipeline cost distribution\n",
                f"pr_pipeline_costs = ps_pr_jobs.groupby('PIPELINE_ID').agg(COST=('COST', 'sum')).reset_index()\n",
                f"analysis.plot_cost_distribution(\n",
                f"    pr_pipeline_costs['COST'],\n",
                f"    title='Pipeline cost distribution for PR branches',\n",
                f"    bins=60\n",
                f")\n",
                f"\n",
                f"master_pipeline_costs = ps_master_jobs.groupby('PIPELINE_ID').agg(COST=('COST', 'sum')).reset_index()\n",
                f"analysis.plot_cost_distribution(\n",
                f"    master_pipeline_costs['COST'],\n",
                f"    title='Pipeline cost distribution for master branch',\n",
                f"    bins=60\n",
                f")\n"
            ]
        }
    ])
    
    return cells


def create_compute_credits_cells(credit_cost):
    """Create cells for compute credits analysis."""
    import os
    org_name = os.getenv("CIRCLE_PROJECT_USERNAME", "unknown-org")
    cells = create_base_setup_cells(org_name=org_name, report_name="Compute Credits", project_name=None)
    
    cells.extend([
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Load data for compute credits analysis\n",
                f"df = pd.read_csv('/tmp/merged.csv', escapechar='\\\\', na_values=['\\\\N'])\n",
                f"print(f'✅ Loaded {{len(df):,}} rows of data')\n",
                f"\n",
                f"# Filter to valid records\n",
                f"df = df[df['JOB_RUN_NUMBER'].notna()]\n",
                f"df = df[df['COMPUTE_CREDITS'].notna()]\n",
                f"df = df[df['PROJECT_NAME'].notna()]\n",
                f"print(f'📊 Found {{df[\"PROJECT_NAME\"].nunique()}} unique projects')\n"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Compute Credits by Project"]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Aggregate compute credits by project\n",
                f"project_stats = df.groupby('PROJECT_NAME').agg({{\n",
                f"    'COMPUTE_CREDITS': ['sum', 'mean', 'count'],\n",
                f"    'JOB_RUN_NUMBER': 'count'\n",
                f"}}).round(2)\n",
                f"\n",
                f"# Flatten column names\n",
                f"project_stats.columns = ['TOTAL_COMPUTE_CREDITS', 'AVG_CREDITS_PER_JOB', 'CREDIT_RECORDS', 'TOTAL_JOBS']\n",
                f"project_stats = project_stats.reset_index()\n",
                f"\n",
                f"# Add cost calculations\n",
                f"project_stats['TOTAL_COST'] = project_stats['TOTAL_COMPUTE_CREDITS'] * {credit_cost}\n",
                f"project_stats['AVG_COST_PER_JOB'] = project_stats['AVG_CREDITS_PER_JOB'] * {credit_cost}\n",
                f"\n",
                f"# Sort by total compute credits\n",
                f"project_stats = project_stats.sort_values('TOTAL_COMPUTE_CREDITS', ascending=False)\n",
                f"\n",
                f"pp(project_stats.head(10), 'Top 10 Projects by Compute Credits')\n"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Visualize compute credits distribution\n",
                f"analysis.plot_cost_distribution(\n",
                f"    project_stats['TOTAL_COST'],\n",
                f"    title='Distribution of Total Costs by Project',\n",
                f"    bins=30\n",
                f")\n",
                f"\n",
                f"print(f'💰 Total compute credits across all projects: {{project_stats[\"TOTAL_COMPUTE_CREDITS\"].sum():,.0f}}')\n",
                f"print(f'💵 Total estimated cost: ${{project_stats[\"TOTAL_COST\"].sum():,.2f}}')\n"
            ]
        }
    ])
    
    return cells


def create_resource_analysis_cells(project_name, credit_cost):
    """Create cells for comprehensive resource utilization analysis notebook."""
    import os
    org_name = os.getenv("CIRCLE_PROJECT_USERNAME", "unknown-org")
    cells = create_base_setup_cells(org_name=org_name, report_name="Resource Class", project_name=project_name)
    
    cells.extend([
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Load and process data\n",
                f"df, project_dfs = analysis.load_circleci_data(\n",
                f"    filepath='/tmp/merged.csv',\n",
                f"    project_name='{project_name}',\n",
                f"    credit_cost={credit_cost}\n",
                f")\n",
                f"\n",
                f"# Extract datasets\n",
                f"ps_jobs = project_dfs['ps_jobs']\n",
                f"print('Dataset loaded successfully')\n",
                f"print(f'Project: {project_name}')\n",
                f"print(f'Total jobs: {{len(ps_jobs):,}}')\n"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Executor and Resource Class Overview"]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Get additional helper function\n",
                f"analyze_executor_resource_combinations = helpers.get('analyze_executor_resource_combinations')\n",
                f"\n",
                f"# Analyze available executor/resource class combinations\n",
                f"if analyze_executor_resource_combinations:\n",
                f"    combo_stats = analyze_executor_resource_combinations(ps_jobs)\n",
                f"    if not combo_stats.empty:\n",
                f"        pp(combo_stats[[\n",
                f"            'EXECUTOR_RESOURCE',\n",
                f"            'UNIQUE_JOBS',\n",
                f"            'TOTAL_RUNS',\n",
                f"            'TOTAL_COST' if 'TOTAL_COST' in combo_stats.columns else 'TOTAL_RUNS',\n",
                f"            'AVG_COST_PER_JOB' if 'AVG_COST_PER_JOB' in combo_stats.columns else 'UNIQUE_JOBS'\n",
                f"        ]], 'Executor and Resource Class Combinations')\n",
                f"    else:\n",
                f"        print('⚠️  No executor/resource class data available')\n",
                f"else:\n",
                f"    print('Analyzing available columns:')\n",
                f"    available_cols = [col for col in ['EXECUTOR', 'RESOURCE_CLASS', 'MEDIAN_CPU_UTILIZATION_PCT', 'MEDIAN_RAM_UTILIZATION_PCT'] if col in ps_jobs.columns]\n",
                f"    print(f'Available columns: {{available_cols}}')\n"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Resource Utilization Analysis Setup"]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Get resource analysis helpers\n",
                f"analyze_resource_utilization = helpers['analyze_resource_utilization']\n",
                f"plot_resource_utilization_scatter = helpers['plot_resource_utilization_scatter']\n",
                f"plot_resource_utilization_distribution = helpers['plot_resource_utilization_distribution']\n",
                f"suggest_resource_optimizations = helpers['suggest_resource_optimizations']\n",
                f"\n",
                f"# Configuration\n",
                f"CPU_THRESHOLD = 40\n",
                f"RAM_THRESHOLD = 40\n",
                f"MIN_JOBS = 5\n",
                f"\n",
                f"print(f'Analysis thresholds: {{CPU_THRESHOLD}}% CPU, {{RAM_THRESHOLD}}% RAM')\n",
                f"print(f'Minimum jobs for analysis: {{MIN_JOBS}}')\n"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Resource Utilization Analysis"]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Perform resource utilization analysis\n",
                f"resource_analysis = analyze_resource_utilization(\n",
                f"    ps_jobs, \n",
                f"    cpu_threshold=CPU_THRESHOLD, \n",
                f"    ram_threshold=RAM_THRESHOLD, \n",
                f"    min_jobs=MIN_JOBS\n",
                f")\n",
                f"\n",
                f"if resource_analysis:\n",
                f"    print('✅ Resource analysis completed')\n",
                f"    total_jobs = len(resource_analysis['job_resource_stats'])\n",
                f"    underutilized_both = len(resource_analysis['underutilized_both'])\n",
                f"    print(f'Job types analyzed: {{total_jobs}}')\n",
                f"    print(f'Underutilized (CPU AND RAM): {{underutilized_both}}')\n",
                f"    \n",
                f"    # Show executor statistics\n",
                f"    if 'executor_stats' in resource_analysis:\n",
                f"        print('\\n📊 Executor Types Found:')\n",
                f"        executor_stats = resource_analysis['executor_stats']\n",
                f"        for _, row in executor_stats.iterrows():\n",
                f"            print(f\"  {{row['EXECUTOR']}}: {{row['UNIQUE_JOBS']}} unique jobs, ${{row['COST_sum']:.2f}} total cost\")\n",
                f"else:\n",
                f"    print('❌ No resource utilization data available')\n"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Jobs with Low CPU and RAM Utilization (by Executor + Resource Class)"]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Display underutilized jobs with executor information\n",
                f"if resource_analysis and not resource_analysis['underutilized_both'].empty:\n",
                f"    underutilized_both = resource_analysis['underutilized_both']\n",
                f"    pp(underutilized_both[[\n",
                f"        'JOB_NAME',\n",
                f"        'EXECUTOR_RESOURCE_CLEAN', \n",
                f"        'MEDIAN_CPU_UTILIZATION_PCT_mean',\n",
                f"        'MEDIAN_RAM_UTILIZATION_PCT_mean',\n",
                f"        'MEDIAN_CPU_UTILIZATION_PCT_count',\n",
                f"        'COST_sum'\n",
                f"    ]].head(20), \n",
                f"    'Jobs with Low CPU AND RAM Utilization (with Executor Info)')\n",
                f"    \n",
                f"    total_waste_cost = underutilized_both['COST_sum'].sum()\n",
                f"    print(f'💰 Total cost of underutilized jobs: ${{total_waste_cost:.2f}}')\n",
                f"    \n",
                f"    # Group by executor type\n",
                f"    if 'EXECUTOR' in underutilized_both.columns:\n",
                f"        executor_waste = underutilized_both.groupby('EXECUTOR')['COST_sum'].sum().sort_values(ascending=False)\n",
                f"        print('\\n📊 Underutilized cost by executor type:')\n",
                f"        for executor, cost in executor_waste.items():\n",
                f"            print(f'  {{executor}}: ${{cost:.2f}}')\n",
                f"else:\n",
                f"    print('✅ No jobs found that underutilize both CPU and RAM')\n"
            ]
        },

        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Executor Type Comparison"]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Compare executor types\n",
                f"if resource_analysis and 'executor_stats' in resource_analysis:\n",
                f"    executor_stats = resource_analysis['executor_stats']\n",
                f"    pp(executor_stats[[\n",
                f"        'EXECUTOR',\n",
                f"        'UNIQUE_JOBS',\n",
                f"        'MEDIAN_CPU_UTILIZATION_PCT_mean',\n",
                f"        'MEDIAN_RAM_UTILIZATION_PCT_mean',\n",
                f"        'COST_sum',\n",
                f"        'COST_mean',\n",
                f"        'JOB_RUN_SECONDS_mean'\n",
                f"    ]].sort_values('COST_sum', ascending=False), \n",
                f"    'Executor Type Performance Comparison')\n",
                f"    \n",
                f"    print('\\n🔍 Executor Analysis:')\n",
                f"    for _, row in executor_stats.iterrows():\n",
                f"        executor = row['EXECUTOR']\n",
                f"        cpu_util = row['MEDIAN_CPU_UTILIZATION_PCT_mean']\n",
                f"        ram_util = row['MEDIAN_RAM_UTILIZATION_PCT_mean']\n",
                f"        avg_cost = row['COST_mean']\n",
                f"        print(f'{{executor.title()}}: {{cpu_util:.1f}}% CPU, {{ram_util:.1f}}% RAM, ${{avg_cost:.2f}} avg cost per job')\n"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Comprehensive Visualizations - CPU vs RAM by Executor + Resource Class"]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Create enhanced scatter plot with executor information\n",
                f"if resource_analysis and 'job_resource_stats' in resource_analysis:\n",
                f"    plot_resource_utilization_scatter(\n",
                f"        resource_analysis['job_resource_stats'],\n",
                f"        title='CPU vs RAM Utilization by Executor and Resource Class',\n",
                f"        color_by='EXECUTOR_RESOURCE_CLEAN'\n",
                f"    )\n",
                f"    \n",
                f"    print('💡 In the scatter plot above:')\n",
                f"    print('- Each color represents a different executor + resource class combination')\n",
                f"    print('- Points in the RED quadrant (bottom-left) are prime optimization targets')\n",
                f"    print('- Compare docker vs machine performance for similar resource classes')\n"
            ]
        },

        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Cost Analysis by Executor + Resource Class"]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Cost distribution analysis\n",
                f"if resource_analysis and 'job_resource_stats' in resource_analysis:\n",
                f"    job_stats = resource_analysis['job_resource_stats']\n",
                f"    \n",
                f"    # Get additional visualization functions\n",
                f"    plot_cost_by_executor_resource = helpers.get('plot_cost_by_executor_resource')\n",
                f"    plot_utilization_vs_cost_scatter = helpers.get('plot_utilization_vs_cost_scatter')\n",
                f"    \n",
                f"    if plot_cost_by_executor_resource:\n",
                f"        plot_cost_by_executor_resource(\n",
                f"            job_stats,\n",
                f"            title='Cost Distribution by Executor + Resource Class'\n",
                f"        )\n",
                f"    \n",
                f"    if plot_utilization_vs_cost_scatter:\n",
                f"        plot_utilization_vs_cost_scatter(\n",
                f"            job_stats,\n",
                f"            title='Resource Utilization vs Cost Analysis'\n",
                f"        )\n"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Executor Performance Comparison Charts"]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Comprehensive executor comparison\n",
                f"if resource_analysis and 'executor_stats' in resource_analysis:\n",
                f"    executor_stats = resource_analysis['executor_stats']\n",
                f"    \n",
                f"    # Get visualization function\n",
                f"    plot_executor_comparison_chart = helpers.get('plot_executor_comparison_chart')\n",
                f"    \n",
                f"    if plot_executor_comparison_chart:\n",
                f"        plot_executor_comparison_chart(\n",
                f"            executor_stats,\n",
                f"            title='Comprehensive Executor Performance Analysis'\n",
                f"        )\n",
                f"    else:\n",
                f"        # Fallback basic comparison\n",
                f"        print('📊 Executor Performance Summary:')\n",
                f"        for _, row in executor_stats.iterrows():\n",
                f"            print(f\"  {{row['EXECUTOR'].title()}}: \"\n",
                f"                  f\"{{row['MEDIAN_CPU_UTILIZATION_PCT_mean']:.1f}}% CPU, \"\n",
                f"                  f\"{{row['MEDIAN_RAM_UTILIZATION_PCT_mean']:.1f}}% RAM, \"\n",
                f"                  f\"${{row['COST_mean']:.2f}} avg cost/job\")\n"
            ]
        },


        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Optimization Recommendations"]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Generate enhanced optimization recommendations\n",
                f"if resource_analysis and 'underutilized_both' in resource_analysis:\n",
                f"    print('🎯 OPTIMIZATION RECOMMENDATIONS')\n",
                f"    print('=' * 50)\n",
                f"    \n",
                f"    suggest_resource_optimizations(\n",
                f"        resource_analysis['underutilized_both'], \n",
                f"        cost_savings_threshold=10\n",
                f"    )\n",
                f"    \n",
                f"    # Additional executor-specific insights\n",
                f"    underutilized = resource_analysis['underutilized_both']\n",
                f"    if not underutilized.empty and 'EXECUTOR' in underutilized.columns:\n",
                f"        print('\\n🔧 EXECUTOR-SPECIFIC RECOMMENDATIONS:')\n",
                f"        print('-' * 50)\n",
                f"        \n",
                f"        docker_jobs = underutilized[underutilized['EXECUTOR'] == 'docker']\n",
                f"        machine_jobs = underutilized[underutilized['EXECUTOR'] == 'machine']\n",
                f"        \n",
                f"        if not docker_jobs.empty:\n",
                f"            docker_cost = docker_jobs['COST_sum'].sum()\n",
                f"            print(f'🐳 Docker Jobs: ${{docker_cost:.2f}} in underutilized costs')\n",
                f"            print('   → Consider smaller docker resource classes (medium → small, large → medium)')\n",
                f"            print(f'   → {{len(docker_jobs)}} job types affected')\n",
                f"            print()\n",
                f"        \n",
                f"        if not machine_jobs.empty:\n",
                f"            machine_cost = machine_jobs['COST_sum'].sum()\n",
                f"            print(f'🖥️  Machine Jobs: ${{machine_cost:.2f}} in underutilized costs')\n",
                f"            print('   → Consider smaller machine resource classes or switching to docker')\n",
                f"            print('   → Machine executors are typically more expensive than docker')\n",
                f"            print(f'   → {{len(machine_jobs)}} job types affected')\n"
            ]
        }
    ])
    
    return cells


def run_notebook_conversion(notebook_path, output_dir, analysis_type):
    """Execute the notebook and convert to HTML."""
    analysis_config = ANALYSIS_TYPES[analysis_type]
    output_file = output_dir / analysis_config['output']
    
    # Get the notebook filename (should be in current directory)
    notebook_name = Path(notebook_path).name
    
    cmd = [
        "jupyter", "nbconvert",
        "--to", "html",
        "--execute",
        "--no-input",  # Hide all code cells, show only outputs
        notebook_name,
        "--output-dir", str(output_dir),
        "--output", analysis_config['output'],
        "--ExecutePreprocessor.timeout=600"  # 10 minute timeout
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    print(f"Working directory: {os.getcwd()}")
    
    try:
        # Run from current directory (src/) where the analysis.py is located
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✅ {analysis_config['title']} generated successfully!")
        print(f"📄 HTML report saved to: {output_file}")
        return output_file
    except subprocess.CalledProcessError as e:
        print(f"❌ Error converting notebook: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        sys.exit(1)


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description='Run CircleCI Usage Analysis')
    parser.add_argument('--type', choices=['job', 'project', 'compute-credits', 'resource'], required=True,
                        help='Type of analysis to run')
    parser.add_argument('--project', help='Project name to analyze (auto-detected if not provided)')
    parser.add_argument('--job', default='deploy', help='Individual job name to analyze (for job analysis)')
    parser.add_argument('--credit-cost', type=float, default=0.0006, help='Cost per credit in dollars')
    parser.add_argument('--data-file', default='/tmp/merged.csv', help='Path to the data file')
    
    args = parser.parse_args()
    
    # Validate data file exists
    if not Path(args.data_file).exists():
        print(f"❌ Data file not found: {args.data_file}")
        print("Please ensure the merged.csv file is available")
        sys.exit(1)
    
    print(f"🚀 Starting {ANALYSIS_TYPES[args.type]['title']}")
    print("=" * 60)
    
    # Setup environment
    output_dir = setup_environment()
    
    # Determine project name
    if args.type in ['job', 'project', 'resource'] and not args.project:
        print("Auto-detecting project with highest credit usage...")
        args.project = find_highest_credit_project(args.data_file)
    
    # Create minimal notebook using the analysis library
    print(f"Creating {args.type} analysis notebook...")
    notebook_path = run_existing_notebook_with_params(
        analysis_type=args.type,
        project_name=args.project,
        individual_job_name=args.job,
        credit_cost=args.credit_cost
    )
    
    # Run notebook conversion
    print("Converting notebook to HTML...")
    output_file = run_notebook_conversion(notebook_path, output_dir, args.type)
    
    # Clean up temporary file
    if Path(notebook_path).exists():
        os.unlink(notebook_path)
    
    print(f"\n✅ Analysis complete!")
    print(f"📊 View the report at: {output_file}")


if __name__ == "__main__":
    main()
