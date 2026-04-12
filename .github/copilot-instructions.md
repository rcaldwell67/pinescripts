Bootstrap workspace instructions for Copilot agent, following README and project conventions.

# Copilot Coding Standards and Review Instructions

## Purpose
This instruction set ensures all code in this repository adheres to project coding standards, best practices, and maintainability requirements. Use this as a checklist for code review, refactoring, and before merging or deploying changes.

## General Coding Standards
- Use clear, descriptive variable and function names (no abbreviations unless industry standard)
- Write modular, reusable code; avoid duplication
- Add comments for non-obvious logic and all public APIs
- Remove dead, commented-out, or unused code
- Prefer const/let over var (JS/TS)
- Use strict equality (===) in JS/TS
- Prefer arrow functions for callbacks and functional components (React)
- Use destructuring for props and state in React
- Handle errors and edge cases gracefully
- Validate all user input and external data

## React/Frontend
- Use functional components and React hooks
- Keep components small and focused; extract logic to hooks or helpers if reusable
- Use PropTypes or TypeScript for component props (if TypeScript is used)
- Avoid inline styles except for quick prototyping; prefer CSS modules or styled-components
- Ensure accessibility (aria-labels, keyboard navigation, color contrast)
- Use useEffect dependencies correctly; avoid unnecessary re-renders
- Memoize expensive calculations with useMemo/useCallback
- Never fetch the same resource multiple times in parallel

## Python/Backend
- Follow PEP8 style guide
- Use type hints for all function signatures
- Add docstrings to all public functions and modules
- Handle exceptions and log errors
- Use context managers for file/database access
- Avoid global state; prefer dependency injection
- Write unit tests for all new logic

## Testing
- All new features and bugfixes must include tests (unit, integration, or e2e as appropriate)
- Use Playwright for e2e tests (frontend)
- Use pytest or unittest for Python
- Tests must be deterministic and not depend on external state

## Documentation
- Update README and relevant docs for any user-facing or API changes
- Document all environment variables and configuration options
- Keep changelogs up to date

## Review Checklist
- [ ] Code is clean, readable, and follows standards above
- [ ] No duplicate logic or unnecessary complexity
- [ ] All tests pass locally and in CI
- [ ] No console errors or warnings in browser/devtools
- [ ] No security issues (XSS, SQL injection, etc.)
- [ ] Documentation is updated

---

**Copilot and all contributors must follow this instruction set for all code reviews, refactors, and before merging PRs.**