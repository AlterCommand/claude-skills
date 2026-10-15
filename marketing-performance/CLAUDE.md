# Performance Marketing & Paid Media Skills — Agent Instructions

## For All Agents (Antigravity, Claude Code, Codex CLI, OpenClaw)

This directory contains 49 specialized skills for performance marketing, paid ads (Google Ads, Meta Ads, LinkedIn Ads, Reddit Ads), CRO, econometrics (ROAS forecasting, CPA diagnostics, spend allocation), and AI search engine visibility (AEO/GEO).

Originally developed by Ryze AI, these skills provide deep diagnostic and optimization capabilities for paid media campaigns and can connect directly to live Google Ads / Meta Ads / GA4 / Search Console data via the Ryze MCP connector.

### How to Use

1. **Identify the Channel / Need:**
   - **Google Ads:** `google-ads-audit`, `search-term-mining`, `bid-strategy-recommendations`, `quality-score-breakdown`, `keyword-cannibalization-check`, `ad-extension-audit`.
   - **Meta Ads:** `meta-ads-audit`, `creative-fatigue-detection`, `audience-overlap-analysis`, `frequency-cap-recommendations`, `retargeting-window-analysis`, `competitor-creative-analysis`.
   - **B2B / Community Paid Media:** `linkedin-ads-audit`, `reddit-ads-audit`.
   - **Budget, Econometrics & Pacing:** `ad-spend-allocator`, `budget-scenario-planner`, `channel-mix-optimizer`, `pacing-monitor`, `roas-forecasting`, `cpa-diagnostics`, `wasted-spend-finder`.
   - **A/B Testing & CRO:** `ab-test-analyzer`, `ab-test-setup-and-analysis`, `landing-page-audit`, `landing-page-audit-39`.
   - **AI Engine Visibility (AEO/GEO):** `ai-visibility-audit`, `citation-source-gap-finder`, `content-aeo-optimizer`, `brand-answer-monitoring`.
   - **Content & Creatives:** `ad-copy-variant-generator`, `competitor-teardown`, `content-repurposer`, `email-sequence-writer`, `icp-research-assistant`.
   - **Tracking & Reporting:** `utm-tracking-generator`, `client-report-narratives`, `weekly-account-summary`, `anomaly-detection`, `attribution-model-comparison`, `performance-benchmarking`.

2. **Load ONE skill at a time:** Read only the specialist `SKILL.md` needed for the task. Never bulk-load all 49 skills.

3. **Data Access:** Works seamlessly with pasted CSV exports, report metrics, or live data via the Ryze MCP connector (`https://connector.get-ryze.ai/mcp`).

### Anti-Patterns

❌ Don't confuse with `marketing-skill` (which focuses on organic content, copywriting, and general SEO).
❌ Don't bulk-load all 49 skills into prompt context simultaneously.
