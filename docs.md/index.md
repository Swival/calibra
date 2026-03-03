# Calibra User Guide

Calibra is a benchmarking harness for evaluating coding agents. You define a set of coding tasks and a matrix of configurations to test (different models, instructions, skills, MCP servers, and environments) and Calibra runs every combination, collects structured metrics, and produces statistical reports.

Under the hood, Calibra drives [Swival](https://swival.dev) sessions and collects structured metrics about each trial.

## How it works

You give Calibra a set of **tasks** (a prompt, starter files, and an optional verification script) along with a **matrix** of configurations to test. Calibra expands the matrix into every combination (called a "variant"), runs each variant against each task, optionally multiple times, classifies failures, retries transient errors, tracks your budget, and then aggregates the results with statistical summaries. 
Optionally, a **reviewer** can be configured to evaluate agent answers after each run, retrying with feedback until the answer is accepted or max rounds are reached. The output is a set of reports in JSON, Markdown, and CSV, and optionally an interactive web dashboard.

## Core concepts

A **campaign** is a single benchmarking run, defined by a TOML config file. Each campaign contains **tasks**, which are coding challenges with a prompt, workspace files, and an optional verifier. The **matrix** defines the dimensions you want to test across, and each specific combination of dimensions is called a **variant**. A **trial** is one execution of a variant against a task, and you can run multiple **repeats** of the same variant+task pair to measure variance.

## The five matrix dimensions

Every campaign tests across five dimensions. **Model** controls which LLM to use (provider and model name). **Agent instructions** determines the `AGENTS.md` file that guides agent behavior. **Skills** specifies which skill directories are available. **MCP** provides MCP server configurations. And **environment** applies file overlays to the workspace.

Each dimension has one or more labeled variants. Calibra takes the Cartesian product to generate all combinations, then runs each against every task.

## Documentation overview

The [Installation](installation.md) page gets you set up, and the [Quick Start](quickstart.md) walks you through your first campaign in a few minutes. From there, [Writing Tasks](tasks.md) explains how to build tasks for your benchmark, and [Campaign Configuration](configuration.md) is the full TOML config reference. [Running Campaigns](running.md) covers execution, filtering, and resumption, while [Analyzing Results](analysis.md) explains the metrics and reports. The [Web Dashboard](web-dashboard.md) page shows how to browse results interactively, [Advanced Topics](advanced.md) dives into constraints, sampling, budgets, retries, and comparisons, and the [CLI Reference](cli-reference.md) documents every command and flag.
