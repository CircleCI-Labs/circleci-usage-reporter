<h1 align="center">
  <br>
  <a href="https://www.circleci.com/"><img src="./circleci-logo.png" alt="CircleCI" width="200"></a>
  <br>
  Usage API Reporter
  <br>
</h1>

<h4 align="center">Open-source tools and examples for working with CircleCI's <a href="https://circleci.com/docs/api/v2/index.html#tag/Usage" target="_blank">Usage API</a> to optimize costs and improve pipeline performance.</h4>

<p align="center">
  <a href="#introduction">Introduction</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#whats-included">What's Included</a> •
  <a href="#minimum-requirements">Minimum Requirements</a> •
    <a href="#documentation">Documentation</a> •
  <a href="#contributing">Contributing</a>
</p>


> This repository is part of CircleCI Labs - solutions developed by CircleCI's field engineering team based on real customer needs.
> 
> ✅ **Created by Field Engineers @ CircleCI**  
> ✅ **Used by real CircleCI customers**  
> ❌ **NOT officially supported by CircleCI support**

## Introduction

CircleCI's Usage API provides powerful data about your CI/CD pipelines. This toolkit helps you quickly turn that data into actionable insights with ready-to-use scripts, analysis templates, and visualization integrations.

### What you can discover:

* Which jobs are burning through your budget 💰
* Where your pipelines are slowest 🐌
* Which resources are underutilized 📉
* How to right-size your compute classes ⚡

## Quick Start

### Install with pip

#### 1. Install pyenv (if not already installed)

Install pyenv following the [official installation instructions](https://github.com/pyenv/pyenv#installation). Alternatively, you can use any other Python version manager (e.g., conda, asdf).

#### 2. Install Python 3.8+ using pyenv

```bash
pyenv install 3.11.14  # or any 3.8+ version
```

#### 3. Clone and install the package

```bash
git clone git@github.com:CircleCI-Labs/circleci-usage-reporter.git
cd circleci-usage-reporter
pyenv local 3.11.14     # Set Python version for this project
pip install -e .
```

After installation, the `circleci-usage-reporter` command will be available system-wide:

```bash
# View all available commands
circleci-usage-reporter --help

# Get usage report
circleci-usage-reporter get \
  --org-id <your-org-id> \
  --start-date 2024-01-01 \
  --end-date 2024-01-31
```

**Note:** Use `pip install -e .` for an editable install (changes to source code are immediately available) or `pip install .` for a regular install. If you encounter issues with editable installs, ensure you have pip 21.3+ (upgrade with `pip install --upgrade pip`).

### With Docker

```bash
git clone git@github.com:CircleCI-Labs/circleci-usage-reporter.git
cd circleci-usage-reporter
docker build . -t circleci-usage-reporter:latest
docker run --rm circleci-usage-reporter --help
```

## What's Included

* **Utility to download usage data** - Quickly export data from the Usage API
* **Data processing scripts** - Clean and transform raw exports for analysis  
* **Visualization examples** - Templates for popular BI tools and custom dashboards

## Minimum Requirements

* Python 3.8+
* A CircleCI personal API token ([get yours here](https://app.circleci.com/settings/user/tokens))
* An organisation ID (find this in "Organization Settings")

## Documentation

* [**API Reference**](https://circleci.com/docs/api/v2/index.html#tag/Usage) - Usage API endpoints and data schema
* **[Examples](examples/)** - BI tool templates, analysis notebooks, and integration guides

### Ways to Contribute

* Request additions
* Add new visualization templates
* Improve analysis algorithms
* Share real-world optimization stories
* Fix bugs or improve documentation
* Add support for other BI tools