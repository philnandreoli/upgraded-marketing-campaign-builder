---
description: "Use when building or updating React UI in frontend. Covers component design, state management, API integration, and CSS styling standards for frontend files."
applyTo: "frontend/**/*.{js,jsx,ts,tsx,css,scss}"
---

# Frontend React and CSS Instructions

Use these rules for all React and CSS work under `frontend/`.

## React

- Build with functional components and hooks only. Do not introduce class components.
- Keep components focused and composable. Split large components into smaller presentational and container components.
- Co-locate component logic with the component unless it is shared. Move shared behavior into reusable hooks under `frontend/src`.
- Keep side effects in `useEffect` with complete dependency arrays. Avoid effect-driven state when derived values can be computed directly.
- Type all component props and API payloads when working in TypeScript.
- Handle loading, empty, error, and success states explicitly for any async UI.

## CSS and Styling

- Keep styles modular and close to the component they style.
- Use existing design tokens, variables, and spacing scale before introducing new values.
- Prefer class-based styling. Avoid element selectors that can leak styles globally.
- Keep selector specificity low and avoid `!important` except as a last resort.
- Ensure responsive behavior for mobile and desktop layouts.

## Accessibility and UX

- Use semantic HTML first, then ARIA only when needed.
- Every interactive control must be keyboard accessible and have a visible focus state.
- Provide accessible labels for form fields and icon-only controls.
- Respect reduced motion preferences for non-essential animations.

## Quality Bar

- Keep UI text concise and consistent with existing product terminology.
- Reuse existing components and utility patterns before creating new ones.
- Do not leave debug logs or dead code in committed frontend changes.
