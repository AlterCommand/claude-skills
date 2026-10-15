# Dynamic Skills Routing & Context Optimization Rule

## Purpose
Enables access to the comprehensive library of 2,363 local skills without overloading Antigravity's context window.

## Protocol for Utilizing Skills
1. **Never dump full skill instructions eagerly into context.**
2. When the user requests a specialized procedure, domain expertise, or execution of standard workflows (Marketing, Engineering, DevOps, C-Level, Finance, RA/QM):
   - First, invoke the MCP tool `skills_search(query="<task description>", domain="<optional domain>")`.
   - Analyze the Top 3 results (relevance score and summary).
3. **Just-In-Time Loading**:
   - Call `skills_load(skill_id="<matched_skill>", section="rules")` to load only the core operational instructions and checklists into context.
   - If the task requires execution of an existing automation tool, invoke `skills_exec(skill_id="<skill>", script_name="<script.py>", args=[...])`.
4. After completing the task, do not retain full skill texts in memory; rely on the MCP tools for any subsequent workflow steps.
