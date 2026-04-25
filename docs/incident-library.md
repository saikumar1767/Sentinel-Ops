# Incident Library

## Purpose

The incident library gives SentinelOps a stable set of operator-ready profiles that are useful in all three product shapes:

- standalone local console
- repo-local copilot mode
- production-shaped shared deployment

Each profile includes:

- the API endpoint to run
- the request payload
- the expected outcome
- expected root-cause diagnostic behavior
- operator notes and run steps

## Current Library

### Database Pool Exhaustion Workflow

Best full workflow path. Shows evidence gathering, retrieval, deterministic causal analysis, approval pause, durable thread state, saved incident memory, and final workflow completion.

### Network DNS Regression Investigation

Best one-shot investigation path. Shows strong retrieval support, current-versus-previous comparison, regression detection, and cited root-cause diagnostics.

### Deployment Readiness Failure Analysis

Best fast triage path. Shows structured analysis without workflow state.

### Queue Backlog Approval Pause

Best secondary approval example. Shows that approval pauses apply beyond database incidents.

### Service Restart With Missing Log Path

Best resilience example. Shows safe tool failure handling without collapsing the investigation.

## Why It Matters In Repo-Local Mode

When SentinelOps is attached to a project repo, the incident library becomes a reusable proving ground:

- incident profiles can be run against repo-local logs
- the console stays reproducible
- teams can compare "packaged demo" behavior with "my repo" behavior
- workflow and approval paths remain inspectable
- saved incident summaries become retrieval memory when incident-memory indexing is enabled
