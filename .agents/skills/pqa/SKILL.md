```markdown
# pqa Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches the core development patterns and conventions used in the `pqa` TypeScript repository. You'll learn how to structure files, write imports/exports, follow commit message standards, and work with tests. The guide also outlines suggested commands for common workflows to help streamline your development process.

## Coding Conventions

### File Naming
- Use **kebab-case** for all file names.
  - Example: `user-profile.ts`, `data-service.test.ts`

### Import Style
- Use **relative imports** for referencing modules.
  - Example:
    ```typescript
    import { fetchData } from './data-service';
    ```

### Export Style
- Use **named exports** for all modules.
  - Example:
    ```typescript
    // In data-service.ts
    export function fetchData() { /* ... */ }

    // In another file
    import { fetchData } from './data-service';
    ```

### Commit Messages
- Follow the **Conventional Commits** standard.
- Use `feat` as the prefix for new features.
- Commit message length averages 72 characters.
  - Example:
    ```
    feat: add user authentication middleware
    ```

## Workflows

### Feature Development
**Trigger:** When adding a new feature  
**Command:** `/feature`

1. Create a new branch for your feature.
2. Implement the feature using TypeScript, following file naming and import/export conventions.
3. Write or update tests in a corresponding `.test.ts` file.
4. Commit your changes using the `feat` prefix and a clear message.
5. Open a pull request for review.

### Testing
**Trigger:** Before pushing or merging code  
**Command:** `/test`

1. Identify or create test files matching the `*.test.*` pattern.
2. Run the test suite using your preferred test runner (framework not detected; use `ts-node`, `jest`, or similar).
3. Ensure all tests pass before committing.

### Code Review
**Trigger:** When reviewing a pull request  
**Command:** `/review`

1. Check for adherence to file naming, import/export, and commit message conventions.
2. Verify that new or updated features have corresponding tests.
3. Leave feedback or approve the pull request.

## Testing Patterns

- Test files are named using the `*.test.*` pattern (e.g., `user-profile.test.ts`).
- The specific testing framework is not detected; use a TypeScript-compatible runner.
- Place test files alongside the modules they test or in a dedicated `tests` directory.
- Example test file:
  ```typescript
  import { fetchData } from './data-service';

  describe('fetchData', () => {
    it('should return expected data', () => {
      // test implementation
    });
  });
  ```

## Commands
| Command     | Purpose                                   |
|-------------|-------------------------------------------|
| /feature    | Start a new feature development workflow  |
| /test       | Run the test suite                       |
| /review     | Begin code review for a pull request      |
```