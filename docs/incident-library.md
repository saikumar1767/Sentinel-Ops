# Incident Library

## Purpose

The incident library gives SentinelOps a stable set of operator-ready incident profiles. Each profile includes:
- the API endpoint to run
- the exact request payload
- the expected incident outcome
- operator notes and run steps

## Current library

### Database Pool Exhaustion Workflow

Best full workflow path. Shows evidence gathering, retrieval, approval pause, and final workflow completion.

### Network DNS Regression Investigation

Best one-shot investigation path. Shows strong retrieval support and current-versus-previous comparison.

### Deployment Readiness Failure Analysis

Best fast triage path. Shows structured analysis without workflow state.

### Queue Backlog Approval Pause

Best secondary approval example. Shows that approval pauses apply beyond database incidents.

### Service Restart With Missing Log Path

Best resilience example. Shows safe tool failure handling without collapsing the investigation.
