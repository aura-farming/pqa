```markdown
# pqa Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches the core development patterns and conventions used in the `pqa` Python codebase. You'll learn how to structure files, write imports and exports, follow commit message standards, and understand the project's testing approach. This guide is ideal for contributors seeking to maintain consistency and quality in their work.

## Coding Conventions

### File Naming
- Use **snake_case** for all file names.
  - Example: `data_processor.py`, `utils/helpers.py`

### Import Style
- Use **relative imports** within the package.
  - Example:
    ```python
    from .utils import helper_function
    ```

### Export Style
- Use **named exports** (explicitly define what is exported).
  - Example:
    ```python
    __all__ = ['main_function', 'HelperClass']
    ```

### Commit Messages
- Follow the **conventional commit** format.
- Use the `fix` prefix for bug fixes.
- Keep commit messages concise (average length: ~53 characters).
  - Example:
    ```
    fix: handle edge case in data parsing
    ```

## Workflows

### Making a Bug Fix
**Trigger:** When you need to fix a bug in the codebase  
**Command:** `/fix-bug`

1. Create a new branch for your fix.
2. Make code changes following the coding conventions.
3. Write a commit message starting with `fix:`, describing the change.
4. Push your branch and open a pull request.

### Adding a New Module
**Trigger:** When you need to add a new feature or module  
**Command:** `/add-module`

1. Create a new Python file using snake_case naming.
2. Use relative imports for internal dependencies.
3. Define `__all__` in the module for named exports.
4. Add or update tests as needed.
5. Commit your changes with a conventional commit message.

## Testing Patterns

- Test files follow the pattern `*.test.ts`.
- The testing framework is **unknown**; review existing test files for structure.
- Place test files alongside or near the modules they test.

**Example test file name:**
```
data_processor.test.ts
```

## Commands
| Command      | Purpose                                   |
|--------------|-------------------------------------------|
| /fix-bug     | Start the bug fix workflow                |
| /add-module  | Start the new module creation workflow    |
```
