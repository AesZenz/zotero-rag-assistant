# Skill: docs-update

Orchestrates documentation updates when a component is added or modified.
Reference this skill by name in Claude Code: "follow docs-update.md".

---

## Step 0 — Classify the change

Identify which row applies before touching any file:

| Change type | Label |
|---|---|
| Bug fix or behaviour change inside an existing module, no new pixi task | **FIX** |
| New module added (new file under `src/`), with or without a new pixi task | **NEW** |
| New module that also changes the system topology visible in the SVG (new layer, new external dependency, new data-flow path) | **NEW+SVG** |
| Frontend or other architecturally significant addition that changes the README prose description | **TOPOLOGY** |

If unsure, ask before proceeding.

---

## FIX path

1. **`PROJECT_STATUS.md`** — add a dated entry to Update Log; update Current State paragraph if behaviour changed.
2. **`docs/usage.rst`** — update task documentation if a pixi task's flags, env vars, or prerequisites changed.

Stop here. No other files need touching.

---

## NEW path

Run these steps in order:

1. **`PROJECT_STATUS.md`**
   - Add dated entry to Update Log describing the new file(s) and what they do.
   - Add a row to the What's Built table.
   - Update the Current State paragraph to reflect the new capability.

2. **`README.md`**
   - Add a row to the What's Built table (same content as PROJECT_STATUS, condensed).
   - If a new pixi task was added: add it to the relevant section under Setup → Query or a new section if needed.

3. **`docs/modules/<group>.rst`**
   - Add an `automodule` directive for the new module under the appropriate group file.
   - If no suitable group exists, create a new `.rst` file and add it to `docs/index.rst`'s toctree.

4. **`docs/usage.rst`**
   - If a new pixi task was added: document it with its env vars, flags, and any prerequisites (e.g. background processes required).

Stop here — unless the new module adds a top-level directory that should appear in the SVG (e.g. `tests/`), in which case use NEW+SVG instead.

---

## NEW+SVG path

Run all four NEW steps above, then:

5. **SVG diagram** — follow `.claude/skills/diagram-update.md` to regenerate `docs/architecture_gh_opt.svg`.
   - The README already references the SVG by path; no README prose change is needed unless the architecture description paragraph is now factually wrong.
   - After verifying the SVG looks correct, rebuild the Sphinx HTML with `pixi run -e docs docs` to reflect the change in the docs site.

---

## TOPOLOGY path (frontend or major structural change)

Run all NEW+SVG steps, then:

6. **`README.md` architecture prose** — update the paragraph below the SVG image that describes Ingestion / Retrieval / Generation layers. This step requires human judgment; do not auto-generate it. Draft a replacement and ask for review before writing to file.

---

## Checklist summary

| Step | FIX | NEW | NEW+SVG | TOPOLOGY |
|---|---|---|---|---|
| PROJECT_STATUS.md update log + current state | ✅ | ✅ | ✅ | ✅ |
| PROJECT_STATUS.md What's Built table | ❌ | ✅ | ✅ | ✅ |
| README.md What's Built table | ❌ | ✅ | ✅ | ✅ |
| README.md pixi task docs | ❌ | if new task | if new task | if new task |
| docs/modules/*.rst automodule | ❌ | ✅ | ✅ | ✅ |
| docs/usage.rst pixi task docs | if changed | if new task | if new task | if new task |
| SVG regeneration (diagram-update.md) | ❌ | ❌ | ✅ | ✅ |
| Sphinx rebuild (pixi run -e docs docs) | ❌ | ❌ | ✅ | ✅ |
| README.md architecture prose | ❌ | ❌ | ❌ | ✅ (human review) |

---

## Notes

- Always update PROJECT_STATUS.md first — it is the source of truth; other files derive from it.
- Dates in PROJECT_STATUS.md use `YYYY-MM-DD` format.
- The README What's Built table uses three columns: Component, File, Status (✅ / 🔲).
- The SVG step is self-contained in `diagram-update.md`; do not inline SVG editing here.
- For the TOPOLOGY path, draft the README prose and pause for review — do not write it autonomously.
- **SVG scope:** the diagram is a full repo map, not a runtime-only architecture diagram. All top-level directories with meaningful content belong in it — `src/`, `scripts/`, `docs/`, `tests/`, `data/`. When in doubt, include it.
- **`tests/` directory:** adding or completing the pytest suite is a NEW+SVG path (tests block appears in the SVG). No `docs/modules/*.rst` automodule entry — Sphinx autodoc does not document test code.
- **Sphinx rebuild:** the HTML build in `docs/_build/` is not auto-updated; it must be rebuilt explicitly after source changes. The rebuild step is intentionally manual so the SVG can be verified before the HTML is generated.
