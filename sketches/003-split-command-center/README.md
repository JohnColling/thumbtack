## Variant: Split Command Center

### Design stance
Three-pane layout: sidebar for navigation, center for the primary task console, right pane as a dedicated status feed. Inspired by command centers and IDE layouts — everything visible without scrolling.

### Key choices
- Layout: 56px sidebar + fluid center + fixed 288px right pane. Right pane contains agent mini-cards with vertical status bars and a webhook log. Center is a focused task table with compact KPI rings.
- Typography: Space Grotesk — geometric, slightly technical, with personality.
- Color: Deep void (#0a0a0f) with purple accent (#a78bfa). Status bars replace dots for stronger visual encoding. Rounded KPI rings show counts at a glance.
- Interaction: Same functional suite but optimized for dense information display. Agent cards in the right pane are clickable and hoverable.

### Trade-offs
- Strong at: Maximum information density. Everything important is always visible. Great for monitoring.
- Weak at: Narrow center pane cramps the task table on smaller screens. Right pane can feel crowded with 10+ agents.

### Best for
Ops dashboards, NOC-style monitoring, users who want to see everything at once without scrolling or clicking between views.