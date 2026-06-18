# Storybook

The web app uses Storybook for component-first UI iteration. It is configured
with the React Vite framework in `web/.storybook` and loads the same global CSS
as the production app.

## Commands

```sh
cd web
bun run storybook
bun run build-storybook
```

`bun run storybook` serves Storybook on `http://127.0.0.1:6006` by default.
`bun run build-storybook` writes `web/storybook-static`, which is ignored by git.

## Coverage

Stories are grouped by component family:

- `Design System/Component Inventory`
- `Design System/UI Primitives`
- `Design System/Workbench Components`
- `Features/Documents`
- `Features/Diagnostics`

When a shared UI primitive, workbench component, document surface, or
diagnostics surface changes, add or update a story in the same change.

## Data policy

Storybook must not use live API data from `http://localhost:8765` or copied
values from a local DuckDB corpus. All stories use synthetic fixtures under
`web/src/stories/fixtures`. Keep filenames, paths, file hashes, OCR text,
diagnostic errors, and timestamps fake and non-identifying.
