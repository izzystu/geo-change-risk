# Testing Documentation

This folder contains test procedures and runbooks for the Geo Change Risk Platform.

## Test Categories

| Category | Type | Location |
|----------|------|----------|
| Local Setup | Manual | [local-setup-runbook.md](./local-setup-runbook.md) |
| API Endpoints | Manual/Automated | TBD |
| Raster Pipeline | Manual/Automated | TBD |
| Web UI | Manual | TBD |

## Running Manual Tests

Manual test runbooks use checkboxes that can be:
1. Copied into a GitHub issue for tracking
2. Used as a pre-release checklist
3. Assigned to team members for execution

### Creating a Test Issue

1. Open a new GitHub issue
2. Copy the relevant runbook's checklist section
3. Assign to a tester
4. Check off items as completed
5. Note any failures in comments

## Test Environments

| Environment | Purpose | Setup |
|-------------|---------|-------|
| Local | Development testing | `./setup.ps1` or `./setup.sh` |
| CI | Automated checks | GitHub Actions (planned) |
| Staging | Pre-release validation | TBD |

## Writing New Runbooks

Use [manual-test-template.md](./manual-test-template.md) as a starting point for new test procedures.

Key principles:
- **Reproducible** - Clear prerequisites and clean state requirements
- **Observable** - Specific expected outcomes, not vague "should work"
- **Independent** - Each test can run without prior tests
- **Traceable** - Link to related code, issues, or requirements
