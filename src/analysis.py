#!/usr/bin/env python3
"""
CircleCI Usage Analysis Library

This module provides common functionality for analyzing CircleCI usage data,
including data loading, preprocessing, visualization, and helper functions.
Used by multiple analysis notebooks to reduce duplication.
"""

import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display, HTML
import warnings

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

# === CONFIGURATION ===


def setup_pandas_display():
    """Configure pandas display options for better notebook output."""
    pd.set_option("display.max_colwidth", None)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.colheader_justify", "left")
    pd.set_option('display.precision', 2)


def setup_matplotlib():
    """Configure matplotlib for notebook environments."""
    # Use inline backend for Jupyter notebooks
    try:
        from IPython import get_ipython
        ipython = get_ipython()
        if ipython is not None:
            ipython.run_line_magic('matplotlib', 'inline')
    except Exception:
        # Fallback for non-notebook environments
        import matplotlib
        matplotlib.use('Agg')
    
    plt.style.use('default')
    plt.rcParams['figure.figsize'] = (12, 6)
    plt.rcParams['font.size'] = 10
    # Ensure plots are embedded properly in notebooks
    plt.rcParams['figure.dpi'] = 100
    plt.rcParams['savefig.dpi'] = 100
    plt.rcParams['savefig.bbox'] = 'tight'
    plt.rcParams['savefig.format'] = 'png'


def _display_plot():
    """Helper function to properly display plots in notebooks and HTML output."""
    plt.tight_layout()
    # Ensure proper embedding in notebooks and HTML output
    try:
        # Try to use IPython display if available
        from IPython.display import display, Image
        import io
        
        # Save figure to bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        
        # Display the image
        display(Image(buf.getvalue()))
        buf.close()
        plt.close()
    except ImportError:
        # Fallback to regular show
        plt.show()


def setup_jupyter_css():
    """Apply custom CSS styling for tables."""
    return HTML("""
    <style>
    .dataframe {
        font-family: monospace;
    }
    .dataframe th {
        background: #3f577c; 
        font-family: monospace; 
        color: white; 
        border: 1px solid white; 
        text-align: left !important;
    }
    </style>
    """)

# === DATA LOADING AND PREPROCESSING ===


def load_circleci_data(filepath, project_name=None, credit_cost=0.0006):
    """
    Load and preprocess CircleCI usage data from CSV file.
    
    Args:
        filepath (str): Path to the CSV data file
        project_name (str, optional): Filter data to specific project
        credit_cost (float): Cost per credit in dollars
        
    Returns:
        tuple: (full_df, project_specific_dfs_dict)
    """
    print(f"Loading CircleCI data from: {filepath}")
    
    # Load CSV data
    na_values = ["\\N"]
    df = pd.read_csv(filepath, escapechar="\\", na_values=na_values)
    
    print(f"✅ Loaded {len(df):,} rows of data")
    if 'PIPELINE_CREATED_AT' in df.columns:
        print(f"📊 Date range: {df['PIPELINE_CREATED_AT'].min()} to {df['PIPELINE_CREATED_AT'].max()}")
    
    # Process datetime columns
    datetime_columns = [
        "LAST_BUILD_FINISHED_AT", "PIPELINE_CREATED_AT", "WORKFLOW_FIRST_JOB_QUEUED_AT",
        "WORKFLOW_FIRST_JOB_STARTED_AT", "WORKFLOW_STOPPED_AT", 
        "JOB_RUN_STARTED_AT", "JOB_RUN_STOPPED_AT"
    ]
    
    for col in datetime_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="ISO8601", errors='coerce')
    
    # Add computed fields
    df = add_computed_fields(df, credit_cost)
    
    # Clean up unnecessary columns
    df = remove_unnecessary_columns(df)
    
    # Create project-specific datasets if project_name provided
    project_dfs = {}
    if project_name:
        project_dfs = create_project_datasets(df, project_name)
    
    return df, project_dfs


def add_computed_fields(df, credit_cost):
    """Add computed fields to the dataframe."""
    # Cost calculation
    if 'TOTAL_CREDITS' in df.columns and 'USER_CREDITS' in df.columns:
        df["COST"] = (df["TOTAL_CREDITS"] - df["USER_CREDITS"]) * credit_cost
    elif 'COMPUTE_CREDITS' in df.columns:
        df["COST"] = df["COMPUTE_CREDITS"] * credit_cost
    
    # Job duration
    if 'JOB_RUN_SECONDS' in df.columns:
        df['DURATION'] = pd.to_timedelta(df['JOB_RUN_SECONDS'], unit='s')
    
    # Job URL
    df["JOB_URL"] = df.apply(_create_job_url, axis=1)
    
    return df


def _create_job_url(row):
    """Create CircleCI job URL from row data."""
    try:
        return "https://app.circleci.com/pipelines/github/{org_slug}/{project_slug}/{pipeline_num}/workflows/{workflow_id}/jobs/{job_num}".format(
            org_slug=row.get("ORGANIZATION_NAME", ""),
            project_slug=row.get("PROJECT_NAME", ""),
            pipeline_num=row.get('PIPELINE_NUMBER', ''),
            workflow_id=row.get("WORKFLOW_ID", ""),
            job_num=int(row.get("JOB_RUN_NUMBER", 0)) if pd.notna(row.get("JOB_RUN_NUMBER")) else 0,
        )
    except (ValueError, TypeError):
        return "N/A"


def remove_unnecessary_columns(df):
    """Remove columns that aren't needed for analysis."""
    columns_to_remove = [
        "ORGANIZATION_ID", 
        "ORGANIZATION_CREATED_DATE",
        "PROJECT_ID", "PROJECT_CREATED_DATE", "VCS_NAME", "VCS_URL",
        "IS_UNREGISTERED_USER", "PIPELINE_TRIGGER_SOURCE",
    ]
    # Only remove columns that actually exist
    existing_cols_to_remove = [col for col in columns_to_remove if col in df.columns]
    if existing_cols_to_remove:
        df = df.drop(columns=existing_cols_to_remove)
    return df


def create_project_datasets(df, project_name):
    """Create project-specific filtered datasets."""
    # Base project data
    ps_jobs = df[(df["PROJECT_NAME"] == project_name) & (df["JOB_RUN_NUMBER"].notna())]
    
    # Master branch-specific datasets
    ps_master_jobs = ps_jobs[ps_jobs["VCS_BRANCH"] == "master"]
    ps_master_failed_jobs = ps_master_jobs[ps_master_jobs["JOB_BUILD_STATUS"] == "failed"]
    
    # PR branch-specific datasets (exclude test branches)
    ps_pr_jobs = ps_jobs[
        (ps_jobs["VCS_BRANCH"] != "master") & 
        (~ps_jobs["VCS_BRANCH"].str.startswith('test/', na=False))
    ]
    ps_pr_passed_jobs = ps_pr_jobs[ps_pr_jobs["JOB_BUILD_STATUS"] == "success"]
    ps_pr_failed_jobs = ps_pr_jobs[ps_pr_jobs["JOB_BUILD_STATUS"] == "failed"]
    
    return {
        'all_jobs': df,
        'ps_jobs': ps_jobs,
        'ps_master_jobs': ps_master_jobs,
        'ps_master_failed_jobs': ps_master_failed_jobs,
        'ps_pr_jobs': ps_pr_jobs,
        'ps_pr_passed_jobs': ps_pr_passed_jobs,
        'ps_pr_failed_jobs': ps_pr_failed_jobs,
    }


def summarize_dataset(dataframe, name="Dataset"):
    """Generate a summary string for a dataset."""
    if dataframe.empty:
        return f"{name}: No data"
    
    num_jobs = len(dataframe)
    num_pipelines = dataframe["PIPELINE_ID"].nunique() if "PIPELINE_ID" in dataframe.columns else "Unknown"
    
    if "PIPELINE_CREATED_AT" in dataframe.columns:
        max_date = dataframe["PIPELINE_CREATED_AT"].max().date()
        min_date = dataframe["PIPELINE_CREATED_AT"].min().date() 
        range_in_days = (max_date - min_date).days
    else:
        max_date = min_date = range_in_days = "Unknown"
    
    total_cost = dataframe["COST"].sum() if "COST" in dataframe.columns else 0
    
    parts = [
        f"{num_jobs:,} jobs from {num_pipelines} pipelines",
        f"{range_in_days} day period ({min_date} to {max_date})" if range_in_days != "Unknown" else "",
        f"total cost ${total_cost:,.0f}" if total_cost > 0 else ""
    ]
    
    return f"{name}: " + " - ".join(filter(None, parts))

# === HELPER FUNCTIONS FOR DISPLAY ===


def code(val: str):
    """Format a value as code."""
    if pd.isna(val):
        return "<code>N/A</code>"
    return f"<code>{val}</code>"


def duration(delta):
    """Format a timedelta as HH:MM:SS."""
    if pd.isna(delta):
        return "<code>N/A</code>"
    
    try:
        total_seconds = delta.total_seconds()
        num_hours = int(total_seconds // 3600)
        num_minutes = int((total_seconds - 3600 * num_hours) // 60)
        num_seconds = int(total_seconds - 3600 * num_hours - 60 * num_minutes)
        return f"<code>{num_hours:02}:{num_minutes:02}:{num_seconds:02}</code>"
    except (ValueError, AttributeError):
        return f"<code>Error: {delta}</code>"


def dollar_amount(val):
    """Format a value as currency."""
    if pd.isna(val):
        return "$0.00"
    return f"${val:.2f}"


def pp(df, title=""):
    """Pretty-print a dataframe with custom formatting."""
    if title:
        display(HTML(f"<h4>{title}</h4>"))
    
    formatters = {
        "JOB_NAME": code,
        "DURATION": duration,
        "AVG_DURATION": duration,
        "P95_DURATION": duration,
        "TOTAL_DURATION": duration,
        "AVG_COST": dollar_amount,
        "COST": dollar_amount,
        "TOTAL_COST": dollar_amount,
    }
    
    # Only use formatters for columns that exist
    active_formatters = {k: v for k, v in formatters.items() if k in df.columns}
    
    display(HTML(df.to_html(
        index=False, 
        render_links=True,
        formatters=active_formatters,
        escape=False
    )))

# === ANALYSIS FUNCTIONS ===


def percentile(n):
    """Create a percentile function for pandas aggregations."""
    def percentile_(x):
        return x.quantile(n)
    percentile_.__name__ = f'percentile_{n*100:02.0f}'
    return percentile_


def group_by_job_name(base_df, status=""):
    """Create aggregated statistics grouped by job name."""
    if status:
        base_df = base_df[base_df["JOB_BUILD_STATUS"] == status]
    
    return base_df.groupby("JOB_NAME").agg(
        NUM_JOBS=("JOB_RUN_NUMBER", "count"),
        # Duration stats
        AVG_DURATION=("DURATION", "mean") if "DURATION" in base_df.columns else ("JOB_RUN_SECONDS", lambda x: pd.to_timedelta(x.mean(), unit='s')),
        P95_DURATION=("DURATION", percentile(0.95)) if "DURATION" in base_df.columns else ("JOB_RUN_SECONDS", lambda x: pd.to_timedelta(x.quantile(0.95), unit='s')),
        TOTAL_DURATION=("DURATION", "sum") if "DURATION" in base_df.columns else ("JOB_RUN_SECONDS", lambda x: pd.to_timedelta(x.sum(), unit='s')),
        # Cost stats
        AVG_COST=("COST", "mean") if "COST" in base_df.columns else pd.NA,
        TOTAL_COST=("COST", "sum") if "COST" in base_df.columns else pd.NA,
    ).reset_index()


def analyse_jobs(df, title_prefix="Job", min_jobs=100):
    """Analyze job performance with various metrics."""
    # Filter jobs that have been run enough times for meaningful analysis
    _df = df[df["NUM_JOBS"] > min_jobs] if "NUM_JOBS" in df.columns else df
    
    if _df.empty:
        print(f"⚠️  No jobs found with more than {min_jobs} runs")
        return
    
    # Various analyses
    analyses = [
        ("slowest AVERAGE duration", "AVG_DURATION", ["JOB_NAME", "AVG_DURATION", "P95_DURATION", "NUM_JOBS"]),
        ("slowest P95 duration", "P95_DURATION", ["JOB_NAME", "AVG_DURATION", "P95_DURATION", "NUM_JOBS"]),
        ("highest TOTAL duration", "TOTAL_DURATION", ["JOB_NAME", "TOTAL_DURATION", "NUM_JOBS"]),
        ("highest AVERAGE cost", "AVG_COST", ["JOB_NAME", "AVG_COST", "NUM_JOBS"]),
        ("highest TOTAL cost", "TOTAL_COST", ["JOB_NAME", "TOTAL_COST", "NUM_JOBS"]),
        ("highest frequency", "NUM_JOBS", ["JOB_NAME", "NUM_JOBS"]),
    ]
    
    for desc, sort_col, display_cols in analyses:
        if sort_col in _df.columns:
            available_cols = [col for col in display_cols if col in _df.columns]
            pp(
                _df.sort_values(sort_col, ascending=False)[available_cols][:10],
                f"{title_prefix} sorted by {desc}"
            )

# === VISUALIZATION FUNCTIONS ===


def use_durations_on_y_axis():
    """Format y-axis to show durations in HH:MM:SS format."""
    ax = plt.gca()
    
    def format_duration_axis(x, p):
        hours = int(x // 3600)
        minutes = int((x % 3600) // 60)
        seconds = int(x % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    from matplotlib.ticker import FuncFormatter
    ax.yaxis.set_major_formatter(FuncFormatter(format_duration_axis))


def plot_cost_distribution(costs, title="Cost Distribution", max_xvalue=None, bins=50):
    """Plot cost distribution with descriptive statistics."""
    if costs.empty:
        print(f"⚠️  No data available for {title}")
        return
    
    # Filter out extreme values if max_xvalue is provided
    if max_xvalue:
        costs = costs[costs <= max_xvalue]
    
    plt.figure(figsize=(12, 6))
    plt.hist(costs, bins=bins, alpha=0.7, edgecolor='black', color='skyblue')
    plt.title(title)
    plt.xlabel('Cost ($)')
    plt.ylabel('Frequency')
    plt.grid(True, alpha=0.3)
    
    # Add statistics
    mean_cost = costs.mean()
    median_cost = costs.median()
    plt.axvline(mean_cost, color='red', linestyle='--', alpha=0.8, label=f'Mean: ${mean_cost:.2f}')
    plt.axvline(median_cost, color='green', linestyle='--', alpha=0.8, label=f'Median: ${median_cost:.2f}')
    plt.legend()
    
    _display_plot()
    
    # Print statistics
    print(f"Count: {len(costs):,}")
    print(f"Mean: ${costs.mean():.2f}")
    print(f"Median: ${costs.median():.2f}")
    print(f"95th percentile: ${costs.quantile(0.95):.2f}")
    print(f"Max: ${costs.max():.2f}")


def analyse_durations(durations, title="Duration Analysis", max_xvalue=None, bins=50):
    """Analyze and plot duration distribution."""
    if durations.empty:
        print(f"⚠️  No data available for {title}")
        return
    
    # Convert to seconds if needed
    if hasattr(durations.iloc[0], 'total_seconds'):
        duration_seconds = durations.apply(lambda x: x.total_seconds())
    else:
        duration_seconds = durations
    
    # Filter extreme values if specified
    if max_xvalue:
        duration_seconds = duration_seconds[duration_seconds <= max_xvalue]
    
    plt.figure(figsize=(12, 6))
    plt.hist(duration_seconds, bins=bins, alpha=0.7, edgecolor='black', color='lightcoral')
    plt.title(title)
    plt.xlabel('Duration (seconds)')
    plt.ylabel('Frequency')
    plt.grid(True, alpha=0.3)
    
    # Format x-axis to show durations
    use_durations_on_y_axis()  # This will format the current axis
    
    _display_plot()
    
    # Print statistics in readable format
    def format_seconds(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    print(f"Count:\t\t{len(duration_seconds):,}")
    print(f"Min:\t\t{format_seconds(duration_seconds.min())}")
    print(f"Average:\t{format_seconds(duration_seconds.mean())}")
    print(f"P95:\t\t{format_seconds(duration_seconds.quantile(0.95))}")
    print(f"Max:\t\t{format_seconds(duration_seconds.max())}")

# === RESOURCE UTILIZATION ANALYSIS ===


def analyze_resource_utilization(df, cpu_threshold=40, ram_threshold=40, min_jobs=5):
    """
    Analyze resource utilization by job and resource class.
    
    Args:
        df: DataFrame with CircleCI job data
        cpu_threshold: CPU utilization threshold (%) below which jobs are considered underutilized
        ram_threshold: RAM utilization threshold (%) below which jobs are considered underutilized
        min_jobs: Minimum number of job runs required for analysis
        
    Returns:
        dict: Contains DataFrames for various resource utilization analyses
    """
    
    # Filter to jobs with resource utilization data
    resource_df = df[
        df['MEDIAN_CPU_UTILIZATION_PCT'].notna() & 
        df['MEDIAN_RAM_UTILIZATION_PCT'].notna()
    ].copy()
    
    if resource_df.empty:
        print("⚠️  No resource utilization data available")
        return {}
    
    print(f"📊 Analyzing {len(resource_df):,} jobs with resource utilization data")
    
    # Create combined executor + resource class field for more detailed analysis
    resource_df['EXECUTOR_RESOURCE'] = resource_df.apply(
        lambda row: f"{str(row.get('EXECUTOR', 'unknown'))}/{str(row.get('RESOURCE_CLASS', 'unknown'))}", 
        axis=1
    )
    
    # Also create a cleaner version for display
    resource_df['EXECUTOR_RESOURCE_CLEAN'] = resource_df.apply(
        lambda row: f"{str(row.get('EXECUTOR', 'unknown')).title()} {str(row.get('RESOURCE_CLASS', 'unknown')).title()}", 
        axis=1
    )
    
    # Job-level resource analysis - group by job name and combined executor/resource class
    job_resource_stats = resource_df.groupby(['JOB_NAME', 'EXECUTOR_RESOURCE_CLEAN']).agg({
        'MEDIAN_CPU_UTILIZATION_PCT': ['mean', 'median', 'count'],
        'MEDIAN_RAM_UTILIZATION_PCT': ['mean', 'median', 'count'],
        'MAX_CPU_UTILIZATION_PCT': ['mean', 'median'],
        'MAX_RAM_UTILIZATION_PCT': ['mean', 'median'],
        'COST': ['sum', 'mean'],
        'JOB_RUN_SECONDS': ['mean', 'median'],
        'EXECUTOR': 'first',  # Keep track of the executor type
        'RESOURCE_CLASS': 'first'  # Keep track of the resource class
    }).round(2)
    
    # Flatten column names
    job_resource_stats.columns = ['_'.join(col).strip() for col in job_resource_stats.columns]
    job_resource_stats = job_resource_stats.reset_index()
    
    # Clean up the column names for the executor and resource class
    job_resource_stats.rename(columns={
        'EXECUTOR_first': 'EXECUTOR',
        'RESOURCE_CLASS_first': 'RESOURCE_CLASS'
    }, inplace=True)
    
    # Filter jobs with sufficient runs
    job_resource_stats = job_resource_stats[
        job_resource_stats['MEDIAN_CPU_UTILIZATION_PCT_count'] >= min_jobs
    ]
    
    # Identify underutilized jobs
    underutilized_cpu = job_resource_stats[
        job_resource_stats['MEDIAN_CPU_UTILIZATION_PCT_mean'] < cpu_threshold
    ].sort_values('MEDIAN_CPU_UTILIZATION_PCT_mean')
    
    underutilized_ram = job_resource_stats[
        job_resource_stats['MEDIAN_RAM_UTILIZATION_PCT_mean'] < ram_threshold
    ].sort_values('MEDIAN_RAM_UTILIZATION_PCT_mean')
    
    underutilized_both = job_resource_stats[
        (job_resource_stats['MEDIAN_CPU_UTILIZATION_PCT_mean'] < cpu_threshold) &
        (job_resource_stats['MEDIAN_RAM_UTILIZATION_PCT_mean'] < ram_threshold)
    ].sort_values(['MEDIAN_CPU_UTILIZATION_PCT_mean', 'MEDIAN_RAM_UTILIZATION_PCT_mean'])
    
    # Resource class analysis - now including executor information
    resource_class_stats = resource_df.groupby('EXECUTOR_RESOURCE_CLEAN').agg({
        'MEDIAN_CPU_UTILIZATION_PCT': ['mean', 'median', 'std'],
        'MEDIAN_RAM_UTILIZATION_PCT': ['mean', 'median', 'std'],
        'COST': ['sum', 'mean'],
        'JOB_RUN_SECONDS': ['mean', 'median'],
        'JOB_NAME': 'nunique',  # Number of unique jobs using this resource class
        'EXECUTOR': 'first',
        'RESOURCE_CLASS': 'first'
    }).round(2)
    
    resource_class_stats.columns = ['_'.join(col).strip() for col in resource_class_stats.columns]
    resource_class_stats = resource_class_stats.reset_index()
    resource_class_stats.rename(columns={
        'JOB_NAME_nunique': 'UNIQUE_JOBS',
        'EXECUTOR_first': 'EXECUTOR',
        'RESOURCE_CLASS_first': 'RESOURCE_CLASS'
    }, inplace=True)
    
    # Executor-only analysis for comparison
    executor_stats = resource_df.groupby('EXECUTOR').agg({
        'MEDIAN_CPU_UTILIZATION_PCT': ['mean', 'median'],
        'MEDIAN_RAM_UTILIZATION_PCT': ['mean', 'median'],
        'COST': ['sum', 'mean'],
        'JOB_RUN_SECONDS': ['mean', 'median'],
        'JOB_NAME': 'nunique'
    }).round(2)
    
    executor_stats.columns = ['_'.join(col).strip() for col in executor_stats.columns]
    executor_stats = executor_stats.reset_index()
    executor_stats.rename(columns={'JOB_NAME_nunique': 'UNIQUE_JOBS'}, inplace=True)
    
    return {
        'job_resource_stats': job_resource_stats,
        'underutilized_cpu': underutilized_cpu,
        'underutilized_ram': underutilized_ram,
        'underutilized_both': underutilized_both,
        'resource_class_stats': resource_class_stats,
        'executor_stats': executor_stats,  # NEW: Executor-only stats
        'raw_resource_data': resource_df
    }


def analyze_executor_resource_combinations(df):
    """
    Analyze all available executor and resource class combinations in the data.
    
    Args:
        df: DataFrame with CircleCI job data
        
    Returns:
        DataFrame: Summary of executor/resource class combinations
    """
    if 'EXECUTOR' not in df.columns or 'RESOURCE_CLASS' not in df.columns:
        available_cols = [col for col in ['EXECUTOR', 'RESOURCE_CLASS'] if col in df.columns]
        print(f"⚠️  Missing columns. Available: {available_cols}")
        return pd.DataFrame()
    
    # Create summary of executor/resource class combinations
    combo_stats = df.groupby(['EXECUTOR', 'RESOURCE_CLASS']).agg({
        'JOB_NAME': 'nunique',
        'JOB_RUN_NUMBER': 'count',
        'COST': ['sum', 'mean'] if 'COST' in df.columns else 'count',
        'JOB_RUN_SECONDS': ['mean', 'median'] if 'JOB_RUN_SECONDS' in df.columns else 'count'
    }).round(2)
    
    # Flatten column names
    combo_stats.columns = ['_'.join(col).strip() for col in combo_stats.columns]
    combo_stats = combo_stats.reset_index()
    
    # Create combined name for display
    combo_stats['EXECUTOR_RESOURCE'] = combo_stats['EXECUTOR'] + ' ' + combo_stats['RESOURCE_CLASS'].str.title()
    
    # Rename columns for clarity
    column_renames = {
        'JOB_NAME_nunique': 'UNIQUE_JOBS',
        'JOB_RUN_NUMBER_count': 'TOTAL_RUNS'
    }
    
    if 'COST_sum' in combo_stats.columns:
        column_renames.update({
            'COST_sum': 'TOTAL_COST',
            'COST_mean': 'AVG_COST_PER_JOB'
        })
    
    if 'JOB_RUN_SECONDS_mean' in combo_stats.columns:
        column_renames.update({
            'JOB_RUN_SECONDS_mean': 'AVG_DURATION_SECONDS',
            'JOB_RUN_SECONDS_median': 'MEDIAN_DURATION_SECONDS'
        })
    
    combo_stats.rename(columns=column_renames, inplace=True)
    
    # Sort by total cost if available, otherwise by total runs
    sort_column = 'TOTAL_COST' if 'TOTAL_COST' in combo_stats.columns else 'TOTAL_RUNS'
    combo_stats = combo_stats.sort_values(sort_column, ascending=False)
    
    return combo_stats


def plot_resource_utilization_scatter(df, title="Resource Utilization by Job", color_by='EXECUTOR_RESOURCE_CLEAN'):
    """Create a scatter plot of CPU vs RAM utilization."""
    if df.empty:
        print(f"⚠️  No data available for {title}")
        return
    
    plt.figure(figsize=(14, 8))
    
    # Create scatter plot with different colors for executor/resource class combinations
    if color_by in df.columns:
        unique_categories = df[color_by].unique()
        colors = plt.cm.Set3(range(len(unique_categories)))
        
        for i, category in enumerate(unique_categories):
            category_data = df[df[color_by] == category]
            plt.scatter(
                category_data['MEDIAN_CPU_UTILIZATION_PCT_mean'], 
                category_data['MEDIAN_RAM_UTILIZATION_PCT_mean'],
                label=category, 
                alpha=0.7, 
                s=80,  # Slightly larger dots for better visibility
                color=colors[i],
                edgecolors='black',
                linewidth=0.5
            )
    else:
        # Fallback to original behavior if column doesn't exist
        plt.scatter(
            df['MEDIAN_CPU_UTILIZATION_PCT_mean'], 
            df['MEDIAN_RAM_UTILIZATION_PCT_mean'],
            alpha=0.7, 
            s=80
        )
    
    plt.xlabel('Average CPU Utilization (%)')
    plt.ylabel('Average RAM Utilization (%)')
    plt.title(title)
    plt.grid(True, alpha=0.3)
    
    # Improve legend positioning and styling
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', frameon=True, fancybox=True, shadow=True)
    
    # Add threshold lines with better styling
    plt.axvline(x=40, color='red', linestyle='--', alpha=0.7, linewidth=2, label='40% CPU threshold')
    plt.axhline(y=40, color='red', linestyle='--', alpha=0.7, linewidth=2, label='40% RAM threshold')
    
    # Add quadrant labels for better interpretation
    plt.text(20, 80, 'Low CPU\nHigh RAM', ha='center', va='center', 
             bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.3))
    plt.text(80, 80, 'High CPU\nHigh RAM', ha='center', va='center',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='green', alpha=0.3))
    plt.text(20, 20, 'Low CPU\nLow RAM\n(Optimization Target)', ha='center', va='center',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='red', alpha=0.3))
    plt.text(80, 20, 'High CPU\nLow RAM', ha='center', va='center',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='orange', alpha=0.3))
    
    _display_plot()


def plot_resource_utilization_distribution(utilization_data, resource_type="CPU", bins=30, executor_data=None):
    """Plot distribution of resource utilization with optional executor breakdown."""
    plt.figure(figsize=(14, 6))
    
    if executor_data is not None and 'EXECUTOR' in executor_data.columns:
        # Create stacked histogram by executor type
        executors = executor_data['EXECUTOR'].unique()
        
        executor_data_list = []
        labels = []
        
        for i, executor in enumerate(executors):
            executor_mask = executor_data['EXECUTOR'] == executor
            executor_utilization = utilization_data[executor_mask].dropna()
            if len(executor_utilization) > 0:
                executor_data_list.append(executor_utilization)
                labels.append(f'{executor.title()} ({len(executor_utilization)} jobs)')
        
        if executor_data_list:
            plt.hist(executor_data_list, bins=bins, alpha=0.7, label=labels,
                     edgecolor='black', linewidth=0.5, stacked=False)
            plt.legend()
        else:
            # Fallback to simple histogram
            plt.hist(utilization_data.dropna(), bins=bins, alpha=0.7,
                     edgecolor='black', color='lightblue')
    else:
        # Simple histogram without executor breakdown
        plt.hist(utilization_data.dropna(), bins=bins, alpha=0.7,
                 edgecolor='black', color='lightblue')
    
    plt.title(f'{resource_type} Utilization Distribution')
    plt.xlabel(f'{resource_type} Utilization (%)')
    plt.ylabel('Frequency')
    plt.grid(True, alpha=0.3)
    
    # Add statistics with better positioning
    mean_util = utilization_data.mean()
    median_util = utilization_data.median()
    plt.axvline(mean_util, color='red', linestyle='--', alpha=0.8, linewidth=2, 
                label=f'Mean: {mean_util:.1f}%')
    plt.axvline(median_util, color='green', linestyle='--', alpha=0.8, linewidth=2, 
                label=f'Median: {median_util:.1f}%')
    plt.axvline(40, color='orange', linestyle='--', alpha=0.8, linewidth=2, 
                label='40% threshold')
    
    # Enhance legend
    plt.legend(loc='upper right', frameon=True, fancybox=True, shadow=True)
    
    _display_plot()
    
    # Print statistics with executor breakdown if available
    print(f"Count: {utilization_data.count():,}")
    print(f"Mean: {utilization_data.mean():.1f}%")
    print(f"Median: {utilization_data.median():.1f}%")
    print(f"Jobs below 40%: {(utilization_data < 40).sum():,} ({(utilization_data < 40).mean()*100:.1f}%)")
    
    if executor_data is not None and 'EXECUTOR' in executor_data.columns:
        print("\nBreakdown by executor:")
        for executor in executor_data['EXECUTOR'].unique():
            executor_mask = executor_data['EXECUTOR'] == executor
            executor_utilization = utilization_data[executor_mask]
            if len(executor_utilization) > 0:
                below_40_pct = (executor_utilization < 40).mean() * 100
                print(f"  {executor.title()}: {executor_utilization.mean():.1f}% avg, "
                      f"{len(executor_utilization)} jobs, {below_40_pct:.1f}% below 40%")


def plot_cost_by_executor_resource(df, title="Cost Distribution by Executor + Resource Class"):
    """Create a cost distribution plot broken down by executor and resource class."""
    if df.empty:
        print(f"⚠️  No data available for {title}")
        return
    
    if 'EXECUTOR_RESOURCE_CLEAN' not in df.columns or 'COST_sum' not in df.columns:
        print(f"⚠️  Required columns not found for {title}")
        return
    
    plt.figure(figsize=(14, 8))
    
    # Create box plot of costs by executor + resource class
    categories = df['EXECUTOR_RESOURCE_CLEAN'].unique()
    cost_data = []
    labels = []
    
    for category in categories:
        category_costs = df[df['EXECUTOR_RESOURCE_CLEAN'] == category]['COST_sum']
        if len(category_costs) > 0:
            cost_data.append(category_costs)
            labels.append(f"{category}\n(n={len(category_costs)})")
    
    if cost_data:
        box_plot = plt.boxplot(cost_data, labels=labels, patch_artist=True)
        
        # Color the boxes
        colors = plt.cm.Set3(range(len(cost_data)))
        for patch, color in zip(box_plot['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
    
    plt.title(title)
    plt.ylabel('Total Cost ($)')
    plt.xlabel('Executor + Resource Class')
    plt.xticks(rotation=45, ha='right')
    plt.grid(True, alpha=0.3)
    _display_plot()
    
    # Print summary statistics
    print("Cost summary by executor + resource class:")
    cost_summary = df.groupby('EXECUTOR_RESOURCE_CLEAN')['COST_sum'].agg(['count', 'mean', 'median', 'sum']).round(2)
    cost_summary.columns = ['Job Types', 'Avg Cost', 'Median Cost', 'Total Cost']
    cost_summary = cost_summary.sort_values('Total Cost', ascending=False)
    print(cost_summary)


def plot_utilization_vs_cost_scatter(df, title="Resource Utilization vs Cost"):
    """Create scatter plots showing the relationship between utilization and cost."""
    if df.empty or 'EXECUTOR_RESOURCE_CLEAN' not in df.columns:
        print(f"⚠️  No data available for {title}")
        return
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    # CPU utilization vs cost
    categories = df['EXECUTOR_RESOURCE_CLEAN'].unique()
    colors = plt.cm.Set3(range(len(categories)))
    
    for i, category in enumerate(categories):
        category_data = df[df['EXECUTOR_RESOURCE_CLEAN'] == category]
        ax1.scatter(category_data['MEDIAN_CPU_UTILIZATION_PCT_mean'],
                    category_data['COST_sum'],
                    label=category, alpha=0.7, s=60, color=colors[i],
                    edgecolors='black', linewidth=0.5)
    
    ax1.set_xlabel('Average CPU Utilization (%)')
    ax1.set_ylabel('Total Cost ($)')
    ax1.set_title('CPU Utilization vs Total Cost')
    ax1.grid(True, alpha=0.3)
    ax1.axvline(x=40, color='red', linestyle='--', alpha=0.7, label='40% threshold')
    
    # RAM utilization vs cost
    for i, category in enumerate(categories):
        category_data = df[df['EXECUTOR_RESOURCE_CLEAN'] == category]
        ax2.scatter(category_data['MEDIAN_RAM_UTILIZATION_PCT_mean'],
                    category_data['COST_sum'],
                    label=category, alpha=0.7, s=60, color=colors[i],
                    edgecolors='black', linewidth=0.5)
    
    ax2.set_xlabel('Average RAM Utilization (%)')
    ax2.set_ylabel('Total Cost ($)')
    ax2.set_title('RAM Utilization vs Total Cost')
    ax2.grid(True, alpha=0.3)
    ax2.axvline(x=40, color='red', linestyle='--', alpha=0.7, label='40% threshold')
    
    # Add legend to the right of both plots
    fig.legend(categories, bbox_to_anchor=(1.05, 0.5), loc='center left')
    
    _display_plot()
    
    print("💡 Interpretation:")
    print("- Points in the upper-left quadrant are expensive but underutilized")
    print("- Points in the lower-right quadrant are well-utilized and cost-effective")
    print("- Look for outliers that might need resource class adjustments")


def plot_executor_comparison_chart(executor_stats, title="Executor Performance Comparison"):
    """Create a comprehensive comparison chart of executor types."""
    if executor_stats.empty:
        print(f"⚠️  No data available for {title}")
        return
    
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    
    executors = executor_stats['EXECUTOR']
    colors = plt.cm.Set2(range(len(executors)))
    
    # CPU Utilization comparison
    bars1 = ax1.bar(executors, executor_stats['MEDIAN_CPU_UTILIZATION_PCT_mean'], 
                    color=colors, alpha=0.7, edgecolor='black')
    ax1.set_title('Average CPU Utilization by Executor')
    ax1.set_ylabel('CPU Utilization (%)')
    ax1.axhline(y=40, color='red', linestyle='--', alpha=0.7, label='40% threshold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Add value labels on bars
    for bar, value in zip(bars1, executor_stats['MEDIAN_CPU_UTILIZATION_PCT_mean']):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                 f'{value:.1f}%', ha='center', va='bottom')
    
    # RAM Utilization comparison
    bars2 = ax2.bar(executors, executor_stats['MEDIAN_RAM_UTILIZATION_PCT_mean'], 
                    color=colors, alpha=0.7, edgecolor='black')
    ax2.set_title('Average RAM Utilization by Executor')
    ax2.set_ylabel('RAM Utilization (%)')
    ax2.axhline(y=40, color='red', linestyle='--', alpha=0.7, label='40% threshold')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Add value labels on bars
    for bar, value in zip(bars2, executor_stats['MEDIAN_RAM_UTILIZATION_PCT_mean']):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                 f'{value:.1f}%', ha='center', va='bottom')
    
    # Total Cost comparison
    bars3 = ax3.bar(executors, executor_stats['COST_sum'], 
                    color=colors, alpha=0.7, edgecolor='black')
    ax3.set_title('Total Cost by Executor')
    ax3.set_ylabel('Total Cost ($)')
    ax3.grid(True, alpha=0.3)
    
    # Add value labels on bars
    for bar, value in zip(bars3, executor_stats['COST_sum']):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + value*0.01,
                 f'${value:.0f}', ha='center', va='bottom')
    
    # Average Cost per Job comparison
    bars4 = ax4.bar(executors, executor_stats['COST_mean'], 
                    color=colors, alpha=0.7, edgecolor='black')
    ax4.set_title('Average Cost per Job by Executor')
    ax4.set_ylabel('Average Cost per Job ($)')
    ax4.grid(True, alpha=0.3)
    
    # Add value labels on bars
    for bar, value in zip(bars4, executor_stats['COST_mean']):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + value*0.01,
                 f'${value:.2f}', ha='center', va='bottom')
    
    _display_plot()
    
    print("📊 Executor Performance Summary:")
    for _, row in executor_stats.iterrows():
        print(f"  {row['EXECUTOR'].title()}: "
              f"{row['MEDIAN_CPU_UTILIZATION_PCT_mean']:.1f}% CPU, "
              f"{row['MEDIAN_RAM_UTILIZATION_PCT_mean']:.1f}% RAM, "
              f"${row['COST_mean']:.2f} avg cost/job, "
              f"{row['UNIQUE_JOBS']} unique jobs")


def plot_resource_class_heatmap(df, title="Resource Class Utilization Heatmap"):
    """Create a heatmap showing utilization patterns by executor and resource class."""
    if df.empty or 'EXECUTOR' not in df.columns or 'RESOURCE_CLASS' not in df.columns:
        print(f"⚠️  Required columns not found for {title}")
        return
    
    try:
        import seaborn as sns
        
        # Create pivot table for heatmap
        cpu_pivot = df.pivot_table(
            values='MEDIAN_CPU_UTILIZATION_PCT_mean', 
            index='EXECUTOR', 
            columns='RESOURCE_CLASS', 
            aggfunc='mean'
        )
        
        ram_pivot = df.pivot_table(
            values='MEDIAN_RAM_UTILIZATION_PCT_mean', 
            index='EXECUTOR', 
            columns='RESOURCE_CLASS', 
            aggfunc='mean'
        )
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        # CPU utilization heatmap
        sns.heatmap(cpu_pivot, annot=True, fmt='.1f', cmap='RdYlGn',
                    cbar_kws={'label': 'CPU Utilization (%)'}, ax=ax1)
        ax1.set_title('CPU Utilization by Executor and Resource Class')
        
        # RAM utilization heatmap
        sns.heatmap(ram_pivot, annot=True, fmt='.1f', cmap='RdYlGn',
                    cbar_kws={'label': 'RAM Utilization (%)'}, ax=ax2)
        ax2.set_title('RAM Utilization by Executor and Resource Class')
        
        _display_plot()
        
    except ImportError:
        print("⚠️  Seaborn not available. Creating alternative visualization...")
        
        # Alternative visualization without seaborn
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # Group data for plotting
        grouped = df.groupby(['EXECUTOR', 'RESOURCE_CLASS']).agg({
            'MEDIAN_CPU_UTILIZATION_PCT_mean': 'mean',
            'MEDIAN_RAM_UTILIZATION_PCT_mean': 'mean'
        }).reset_index()
        
        # Create bubble chart
        for i, row in grouped.iterrows():
            ax.scatter(row['MEDIAN_CPU_UTILIZATION_PCT_mean'],
                       row['MEDIAN_RAM_UTILIZATION_PCT_mean'],
                       s=200, alpha=0.7,
                       label=f"{row['EXECUTOR']} {row['RESOURCE_CLASS']}")
            
            # Add labels
            ax.annotate(f"{row['EXECUTOR']}\n{row['RESOURCE_CLASS']}",
                        (row['MEDIAN_CPU_UTILIZATION_PCT_mean'],
                         row['MEDIAN_RAM_UTILIZATION_PCT_mean']),
                        xytext=(5, 5), textcoords='offset points', fontsize=8)
        
        ax.set_xlabel('Average CPU Utilization (%)')
        ax.set_ylabel('Average RAM Utilization (%)')
        ax.set_title('Resource Utilization by Executor and Resource Class')
        ax.grid(True, alpha=0.3)
        ax.axvline(x=40, color='red', linestyle='--', alpha=0.7)
        ax.axhline(y=40, color='red', linestyle='--', alpha=0.7)
        
        _display_plot()


def suggest_resource_optimizations(underutilized_df, cost_savings_threshold=10):
    """
    Suggest resource class optimizations based on utilization patterns.
    
    Args:
        underutilized_df: DataFrame of underutilized jobs
        cost_savings_threshold: Minimum cost ($) to consider for optimization suggestions
    """
    if underutilized_df.empty:
        print("✅ No significantly underutilized jobs found!")
        return
    
    # Focus on jobs with meaningful cost impact
    significant_cost_jobs = underutilized_df[
        underutilized_df['COST_sum'] >= cost_savings_threshold
    ].sort_values('COST_sum', ascending=False)
    
    if significant_cost_jobs.empty:
        print(f"ℹ️  No underutilized jobs found with cost impact >= ${cost_savings_threshold}")
        return
    
    print(f"🎯 Top optimization opportunities (cost >= ${cost_savings_threshold}):")
    print("-" * 80)
    
    for _, job in significant_cost_jobs.head(10).iterrows():
        job_name = job['JOB_NAME']
        resource_class = job.get('EXECUTOR_RESOURCE_CLEAN', f"{job.get('EXECUTOR', 'unknown')} {job.get('RESOURCE_CLASS', 'unknown')}")
        cpu_util = job['MEDIAN_CPU_UTILIZATION_PCT_mean']
        ram_util = job['MEDIAN_RAM_UTILIZATION_PCT_mean']
        total_cost = job['COST_sum']
        avg_duration = job['JOB_RUN_SECONDS_mean'] / 60  # Convert to minutes
        
        print(f"📝 {job_name}")
        print(f"   Resource Class: {resource_class}")
        print(f"   CPU Utilization: {cpu_util:.1f}% | RAM Utilization: {ram_util:.1f}%")
        print(f"   Total Cost: ${total_cost:.2f} | Avg Duration: {avg_duration:.1f} minutes")
        print("   💡 Consider downgrading to a smaller resource class")
        print()

# === JOB DURATION ANALYSIS ===


def analyze_jobs_by_duration(df, min_jobs=5, top_n=10):
    """
    Analyze jobs by their average duration and return the jobs with the highest average duration.
    
    Args:
        df: DataFrame containing job data with JOB_NAME, JOB_RUN_SECONDS, and COST columns
        min_jobs: Minimum number of job runs required for statistical significance (default: 5)
        top_n: Number of top jobs to return (default: 10)
    
    Returns:
        DataFrame with job duration statistics sorted by average duration (descending)
    """
    if df.empty:
        print("⚠️  No job data available for duration analysis")
        return pd.DataFrame()
    
    print(f"📊 Analyzing job durations from {len(df):,} job records")
    
    # Group by job name and calculate duration statistics
    job_duration_stats = df.groupby("JOB_NAME").agg({
        "JOB_RUN_SECONDS": ["mean", "median", "count"],
        "COST": ["sum", "mean"] if "COST" in df.columns else None
    }).round(2)
    
    # Flatten column names
    job_duration_stats.columns = ["_".join(col).strip() for col in job_duration_stats.columns]
    job_duration_stats = job_duration_stats.reset_index()
    
    # Filter jobs with at least min_jobs runs for statistical significance
    job_duration_stats = job_duration_stats[job_duration_stats["JOB_RUN_SECONDS_count"] >= min_jobs]
    
    if job_duration_stats.empty:
        print(f"⚠️  No jobs found with at least {min_jobs} runs")
        return pd.DataFrame()
    
    # Convert duration to minutes for readability
    job_duration_stats["AVG_DURATION_MINUTES"] = job_duration_stats["JOB_RUN_SECONDS_mean"] / 60
    job_duration_stats["MEDIAN_DURATION_MINUTES"] = job_duration_stats["JOB_RUN_SECONDS_median"] / 60
    
    # Sort by average duration (descending) and get top N
    top_duration_jobs = job_duration_stats.sort_values("JOB_RUN_SECONDS_mean", ascending=False).head(top_n)
    
    print(f"✅ Found {len(job_duration_stats):,} job types with at least {min_jobs} runs")
    print(f"📈 Top {len(top_duration_jobs)} jobs by average duration:")
    
    # Display results
    display_columns = [
        "JOB_NAME", 
        "AVG_DURATION_MINUTES", 
        "MEDIAN_DURATION_MINUTES", 
        "JOB_RUN_SECONDS_count"
    ]
    
    # Add cost columns if available
    if "COST_sum" in top_duration_jobs.columns:
        display_columns.extend(["COST_sum", "COST_mean"])
    
    pp(top_duration_jobs[display_columns], f"Top {top_n} Jobs by Longest Average Duration")
    
    # Summary statistics
    if len(top_duration_jobs) > 0:
        threshold_minutes = top_duration_jobs['AVG_DURATION_MINUTES'].iloc[-1]
        print(f"\n📊 Summary: Jobs with average duration over {threshold_minutes:.1f} minutes")
        
        if "COST_sum" in top_duration_jobs.columns:
            total_cost = top_duration_jobs['COST_sum'].sum()
            print(f"💰 Combined cost of these top {len(top_duration_jobs)} slowest job types: ${total_cost:.2f}")
    
    return top_duration_jobs

# === INITIALIZATION FUNCTION ===


def initialize_notebook(setup_display=True, setup_plots=True, setup_styles=True):
    """Initialize notebook environment with common settings."""
    if setup_display:
        setup_pandas_display()
    if setup_plots:
        setup_matplotlib()
    if setup_styles:
        display(setup_jupyter_css())
    
    print("✅ Analysis environment initialized")
    
    return {
        'pp': pp,
        'code': code, 
        'duration': duration,
        'dollar_amount': dollar_amount,
        'percentile': percentile,
        'group_by_job_name': group_by_job_name,
        'analyse_jobs': analyse_jobs,
        'analyze_jobs_by_duration': analyze_jobs_by_duration,
        'summarize_dataset': summarize_dataset,
        'analyze_resource_utilization': analyze_resource_utilization,
        'plot_resource_utilization_scatter': plot_resource_utilization_scatter,
        'plot_resource_utilization_distribution': plot_resource_utilization_distribution,
        'suggest_resource_optimizations': suggest_resource_optimizations,
        'analyze_executor_resource_combinations': analyze_executor_resource_combinations,
        # Enhanced visualization functions
        'plot_cost_by_executor_resource': plot_cost_by_executor_resource,
        'plot_utilization_vs_cost_scatter': plot_utilization_vs_cost_scatter,
        'plot_executor_comparison_chart': plot_executor_comparison_chart,
        'plot_resource_class_heatmap': plot_resource_class_heatmap,
    }