---
name: rate-overall-severity
description: Classifies overall call severity as Minor/Moderate/Major/Critical (5% weight)
version: 1.0.0
author: Team
---

# Rate Overall Severity

## Purpose

Provides an overall severity classification for the call quality issues found.
This is a classification task, not a percentage score.

## Weight

5% of overall score

## Severity Levels

- Minor (score=100): No significant issues, good call
- Moderate (score=75): Some issues that need coaching
- Major (score=25): Serious issues requiring immediate attention
- Critical (score=0): Severe violations requiring disciplinary action
