## Variant: Dark Utilitarian

### Design stance
Dark, high-contrast, tool-first interface inspired by developer dashboards and terminal aesthetics. The content glows against a deep void background — every pixel serves a function.

### Key choices
- Layout: Classic sidebar + main content grid. 4-column stat row, 2/3 + 1/3 split for tasks and agents.
- Typography: Inter (system-adjacent sans). Monospace for IDs and status codes.
- Color: Near-black background (#0b0c10), muted slate text (#c5c6c7), cyan accent (#66fcf1). Status colors are literal: cyan=running, yellow=pending, green=done, red=failed.
- Interaction: Hover states on all rows, dropdown filter, modal for new tasks, toast notifications, live row insertion on task creation.

### Trade-offs
- Strong at: Long sessions, low eye strain, quick status parsing via color.
- Weak at: Can feel cold or impersonal for non-technical users.

### Best for
Power users who stare at this screen for hours. Developers and ops teams who value scannability over warmth.