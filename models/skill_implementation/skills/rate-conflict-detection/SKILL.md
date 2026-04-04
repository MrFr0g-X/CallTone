---
name: rate-conflict-detection
description: Detects escalations, conflicts, and evaluates how the agent handled them (15% weight)
version: 1.0.0
author: Team
---

# Rate Conflict Detection

## Purpose

Identifies whether conflicts or escalations occurred during the call and
evaluates how the agent handled them.

## Weight

15% of overall score

## Scoring Rubric

- 100 = No conflicts, OR conflicts were expertly de-escalated
- 75 = Minor tension handled well, no escalation
- 50 = Conflict present, partially managed
- 25 = Conflict poorly handled, escalation occurred
- 0 = Agent caused or significantly worsened the conflict
