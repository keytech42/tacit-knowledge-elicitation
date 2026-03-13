---
description: Rules for the React frontend
globs: frontend/**
---

# Frontend

React SPA with Vite + TypeScript.

## Structure

- `src/api/client.ts` — HTTP client (fetch wrapper with JWT)
- `src/auth/AuthContext.tsx` — auth context and login
- `src/components/` — shared components, layout, route guards
- `src/pages/` — feature pages

## Adding a Page

1. Create component in `src/pages/`
2. Add route in `App.tsx`
3. Add API functions in `src/api/client.ts`

## Type Checking

```bash
docker compose exec web npx tsc -b --noEmit
```

This matches CI and catches errors vite dev silently ignores. Always run before committing frontend changes.
