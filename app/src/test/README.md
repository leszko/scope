# Testing Guide

## Overview

This project uses two testing frameworks:
- **Vitest** for unit and component tests
- **Playwright** for end-to-end (E2E) tests

## Running Tests

### Unit Tests

```bash
# Run all unit tests once
npm test

# Run tests in watch mode (auto-rerun on file changes)
npm run test:watch

# Run tests with UI
npm run test:ui
```

### E2E Tests

```bash
# Run all E2E tests
npm run test:e2e

# Run E2E tests with UI
npm run test:e2e:ui
```

### Run All Tests

```bash
npm run test:all
```

## Writing Tests

### Unit Tests

Create test files next to the code you're testing with `.test.ts` or `.spec.ts` extension:

```typescript
// src/utils/myUtil.test.ts
import { describe, it, expect } from 'vitest';
import { myFunction } from './myUtil';

describe('myFunction', () => {
  it('should return expected value', () => {
    expect(myFunction('input')).toBe('expected');
  });
});
```

### Component Tests

```typescript
// src/components/MyComponent.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import MyComponent from './MyComponent';

describe('MyComponent', () => {
  it('should render correctly', () => {
    render(<MyComponent />);
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });
});
```

### E2E Tests

Create test files in `src/test/e2e/` directory:

```typescript
// src/test/e2e/app.spec.ts
import { test, expect } from '@playwright/test';

test('app should launch successfully', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/Daydream Scope/);
});
```

## Best Practices

1. **Test Naming**: Use descriptive names that explain what is being tested
2. **Arrange-Act-Assert**: Structure tests with clear setup, execution, and verification
3. **Mock External Dependencies**: Use `vi.mock()` for external modules
4. **Avoid Testing Implementation Details**: Test behavior, not internal structure
5. **Keep Tests Fast**: Unit tests should run in milliseconds
6. **Use Data-Testid**: Add `data-testid` attributes for reliable element selection

## Coverage

Generate coverage reports:

```bash
npm test -- --coverage
```

Coverage reports will be generated in the `coverage/` directory.

## CI/CD Integration

Tests are automatically run in the CI/CD pipeline. All tests must pass before builds are created.
