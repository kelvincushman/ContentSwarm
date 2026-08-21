# ContentSwarm — rules for AI coding agents

These rules are mandatory for every change made to this repository by any
coding agent (Orphus, Pi, or any other harness). AGENTS.md mirrors this file
for harnesses that read that name.

## Attribution

- Author every commit as **Kelvin Lee <kelvin.cushman@gmail.com>**.
- Never add AI co-author trailers, "generated with" lines, or session links
  to commits, code, or docs.

## Mandatory steps for EVERY change (no exceptions)

1. **Branch** — never commit directly to `main`. Use `feat/…` or `fix/…`
   branch names.
2. **Update the documentation with the change, in the same PR**:
   - `README.md` if capabilities, setup, or usage changed
   - `orphus/README.md` + the relevant `orphus/skills/*/SKILL.md` if the CLI
     or API surface changed (skills must stay accurate to the real flags and
     routes)
   - `deploy/AISERVER_SETUP.md` if deployment or environment variables changed
   - This file, if the process itself changes
3. **Open a PR into `main`** — the review gate is:
   - **CodeRabbit** reviews automatically (`.coderabbit.yaml`); address its
     actionable findings before merge
   - **GPT Sol is the final gate** (`.github/workflows/ai-final-gate.yml`);
     a `VERDICT: BLOCK` must be resolved, never overridden
4. **Merge only after both gates pass.**

## Architecture ground rules

- Orphus/Pi is the brain; ContentSwarm is the mobile phone interface. New
  capabilities are exposed through the REST API (`phone_agent/api.py`) and
  the `contentswarm` CLI (`contentswarm_cli.py`) — agents never import
  ContentSwarm's Python modules directly.
- Learn-then-replay is the core pattern: the vision model teaches a workflow
  once (`learn`, recorded in `phone_agent/flows.py`); repeat executions use
  the deterministic replayer — exact presses, no LLM.
- Model routing lives in `orphus/README.md` (coding on gpt-5.6-terra with
  luna/GLM 5.2/Kimi K3 fallbacks; GPT Sol as the final gate). Keep agent
  frontmatter and that table in sync.
- Secrets only via environment (`CONTENTSWARM_API_TOKEN` etc.) — never in
  code, config files, or logs.

## Verification before any PR

- `python -m compileall phone_agent dashboard contentswarm_cli.py run_server.py main.py`
- YAML/JSON artifacts parse; every `orphus/skills/*/SKILL.md` keeps
  `name:` + `description:` frontmatter
- Smoke-test touched API endpoints and CLI commands where possible without
  hardware; on-device behavior is verified per `deploy/AISERVER_SETUP.md`
