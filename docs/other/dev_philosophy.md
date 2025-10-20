# EDGAR CLI Development Philosophy

## Core Principles

**Quality over Speed**: 

This is a solo exploration project where getting it right matters more than
getting it fast. Take time to think through designs and implement them
carefully.

**Embrace Refactoring**: 

Architecture evolution is expected and welcome. Don't be afraid to change
fundamental patterns when better approaches emerge. Half the project is
development, half is discovery.

**Keep It Simple**: 

Avoid committee-style over-engineering. No schema versioning, no complex
compatibility layers, no premature optimization. Build what's needed now,
refactor when we learn more.

**Functional Style**: 

Prefer pure functions, explicit error handling with Result types, and clear
separation of concerns. Functions should tell the story of what they do.

## Development Workflow

**AI-Assisted Exploration**: 

Discuss implementation strategies, explore pros and cons, align on approach,
then implement step by step with full artifacts.

**Command-by-Command Evolution**: 

When refactoring systems like the pipeline protocol, go through each command
systematically. Don't try to change everything at once.

**Centralized Utilities**: 

Build reusable patterns in `shared.py` and use consistently across CLI
commands. Avoid duplication and keep interfaces clean.

**Error Philosophy**: 

Fail fast, fail clearly. Once an error occurs, propagate it through the
pipeline without further processing. Report the first error encountered.

## Anti-Patterns to Avoid

- Backward compatibility for its own sake
- Complex configuration systems
- Premature performance optimization
- Committee-style feature creep
- Schema versioning and migration complexity

## The Joy of Building

This project is built with care and attention to craft. Each function should be
clear, each module should have a single responsibility, and the overall
architecture should feel elegant and discoverable.

Take time to enjoy the process of creating something that works well and feels
good to use.
