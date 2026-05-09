## Variant: Clean Editorial

### Design stance
Bright, airy, and content-forward. Inspired by modern SaaS dashboards like Linear and Notion — whitespace is intentional, borders are subtle, and the hierarchy is purely typographic.

### Key choices
- Layout: Same structural grid as utilitarian but inverted. Rounded cards (16px radius), generous padding, 5-column grid with 3/5 tasks + 2/5 stacked side panels.
- Typography: DM Sans for warmth, JetBrains Mono for data. Breadcrumb header ("Dashboard / Overview") adds editorial depth.
- Color: White cards on light gray (#f7f8fa), near-black text (#1a1d2e). Status pills use soft tinted backgrounds instead of bright dots. No neon accents — everything is muted and harmonious.
- Interaction: Same functional set (modal, dropdown, toast, live insertion) but with softer transitions (cubic-bezier) and blur-backdrop modals.

### Trade-offs
- Strong at: Feels premium and approachable. Great for mixed technical/non-technical teams.
- Weak at: May wash out on poor monitors. Slightly less scannable at a glance than high-contrast dark mode.

### Best for
Teams who want a dashboard that feels like a polished product, not a monitoring tool. Good for presentations and stakeholder demos.