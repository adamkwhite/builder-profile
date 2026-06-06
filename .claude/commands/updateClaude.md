---
description: Update project CLAUDE.md with static project information (NOT session changes)
---

## Important: CLAUDE.md Purpose

**CLAUDE.md is for STATIC project information only, NOT session logs.**

Session-specific changes should go in CHANGELOG.md (see WrapUpForTheDay commands).

## Task
- if the claude code session is new then
    - read FILE /home/adam/Code/CLAUDE.md,
    - if not in /home/adam/Code/CLAUDE.md then read
            FILE /<project>/CLAUDE.MD,
            FILE /<project>/readme.md,
            FILE /<project>/todo.md

- if the claude code session has content related to <project>
    - Update FILE /<project>/CLAUDE.MD ONLY if adding static project information
    - Suggest changes to /home/adam/Code/CLAUDE.md and ask permission to update.

## When to Update CLAUDE.md

**ONLY update CLAUDE.md for these types of changes:**
- Add new major components or architecture
- Change development commands or workflows
- Add new configuration patterns
- Document permanent implementation details
- Update technology stack or dependencies
- Add new APIs or external services

**DO NOT update CLAUDE.md for:**
- Session-specific changes (those go in CHANGELOG.md)
- Bug fixes or features added (those go in CHANGELOG.md)
- Daily progress updates (those go in CHANGELOG.md)

## Updates to consider for <project>/CLAUDE.md

**Project Overview:** A brief description of what the project is and its goals
**Current Status:** Where you are in the development process
**Current Branch:** Which branch we were last working on
**Technology Stack:** Languages, frameworks, and libraries being used, including version information
**Architecture:** Current architecture and design patterns (permanent, not session-specific)
**Development Workflow:** Commands and processes for development
**Configuration Patterns:** How configuration is managed
**Dependencies:** External services, APIs, or libraries that the project relies on
**Known Limitations:** Architectural constraints or permanent limitations

## Note

For session-specific changes, use `/WrapUpForTheDay` which updates CHANGELOG.md following the [Keep a Changelog](https://keepachangelog.com/) format.
