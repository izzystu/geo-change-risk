# [Feature Name] - Test Runbook

> **Last Updated:** YYYY-MM-DD
> **Related Code:** `path/to/code`
> **Estimated Time:** X minutes

## Overview

Brief description of what this runbook tests and why.

## Prerequisites

- [ ] Prerequisite 1
- [ ] Prerequisite 2

## Clean State Requirements

Describe how to reset to a clean state before testing:

```bash
# Commands to reset state
```

## Test Matrix

| Test ID | Scenario | Flags/Config | Expected Result |
|---------|----------|--------------|-----------------|
| T1 | Description | `--flag` | Expected outcome |
| T2 | Description | `--other` | Expected outcome |

---

## Test Procedures

### T1: [Test Name]

**Scenario:** Description of what we're testing

**Steps:**
1. Step one
2. Step two
3. Step three

**Expected Result:**
- Specific observable outcome
- Another outcome

**Verification:**
```bash
# Command to verify
```

---

### T2: [Test Name]

**Scenario:** Description

**Steps:**
1. Step one

**Expected Result:**
- Outcome

---

## Checklist Summary

Copy this section into a GitHub issue for tracking:

```markdown
## [Feature] Test Execution

**Tester:** @username
**Date:** YYYY-MM-DD
**Environment:** Local / CI / Staging

### Results

- [ ] T1: [Test Name]
- [ ] T2: [Test Name]

### Notes

(Record any failures, observations, or environment details)
```

## Troubleshooting

### Common Issue 1

**Symptom:** What you observe
**Cause:** Why it happens
**Solution:** How to fix it
