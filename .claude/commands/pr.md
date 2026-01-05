---
description: Create a well-structured pull request with comprehensive description
argument-hint: [base-branch]
allowed-tools: Bash(git:*), Bash(gh:*)
---

# Create Pull Request

You are creating a comprehensive, well-structured pull request.

## Current State

- Current branch: !`git branch --show-current`
- Base branch: $ARGUMENTS (default: main)
- Recent commits on this branch:

!`git log --oneline origin/main..HEAD 2>/dev/null || git log --oneline -10`

## Changes Summary

!`git diff --stat origin/main..HEAD 2>/dev/null || git diff --stat HEAD~5`

## Instructions

1. **Analyze all commits** on this branch (not just the latest) to understand the full scope of changes

2. **Create the PR** using `gh pr create` with this structure:

```
## Summary
[2-3 sentences describing WHAT changed and WHY]

## Changes
- [Bullet list of key changes, grouped logically]
- [Include file/component names where helpful]

## Type of Change
- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Refactor (code change that neither fixes a bug nor adds a feature)
- [ ] Documentation update

## Testing
[How to test these changes - commands to run, things to verify]

## Screenshots (if applicable)
[Add screenshots for UI changes]

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] Documentation updated (if needed)
- [ ] No new warnings introduced
```

3. **Generate a concise PR title** that follows conventional commits style:
   - `feat: Add user authentication`
   - `fix: Resolve memory leak in worker pool`
   - `refactor: Simplify database queries`
   - `docs: Update API documentation`

4. **Push the branch** if not already pushed, then create the PR

5. **Return the PR URL** when complete

## Important

- Read ALL commits, not just the most recent one
- Group related changes together in the description
- Be specific about what changed and why
- Include testing instructions that reviewers can follow
