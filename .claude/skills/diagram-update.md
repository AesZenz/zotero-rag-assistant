# Skill: Update Architecture Diagram

## What this skill is for
Updating `docs/architecture_gh_opt.svg` in the zotero-rag-assistant repo when new components are added
(e.g. a frontend layer, a new src/ module, a new script). Read this file in full before touching the SVG.

---

## Layout conventions

### Canvas
- `width="800" viewBox="0 0 800 940"` — adjust viewBox height if adding new rows
- White background `#ffffff`
- Font: `-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif`

### Two-column grid
| | x range | width |
|---|---|---|
| Col A (left) | x=40..350 | 310px |
| Gap corridor | x=350..430 | 80px — **arrow routing only, no boxes** |
| Col B (right) | x=430..760 | 330px |

### Row positions (current)
| Layer | y range | Column |
|---|---|---|
| Config | y=20..60 | centred (x=280..520) |
| Ingestion | y=90..260 | A |
| Utils | y=90..134 | B |
| Retrieval | y=280..420 | A |
| Generation | y=280..470 | B |
| Evaluation | y=490..720 | A |
| Scripts | y=490..720 | B |
| Config/env bar | y=752..796 | full width |
| Docs bar | y=832..876 | full width |
| Legend | y=898..910 | full width |

---

## Colour palette (hardcoded — no CSS variables)

| Layer | Outer fill | Outer stroke | Inner fill | Text heading | Text sub |
|---|---|---|---|---|---|
| Ingestion | `#e1f5ee` | `#0f6e56` | `#9fe1cb` | `#085041` | `#0f6e56` |
| Retrieval | `#eeedfe` | `#534ab7` | `#afa9ec` | `#3c3489` | `#534ab7` |
| Generation | `#e6f1fb` | `#185fa5` | `#85b7eb` | `#0c447c` | `#185fa5` |
| Evaluation | `#faeeda` | `#854f0b` | `#fac775` | `#633806` | `#854f0b` |
| Scripts | `#faece7` | `#993c1d` | `#f0997b` | `#712b13` | `#993c1d` |
| Config/utils/infra | `#f1efe8` | `#5f5e5a` | — | `#444441` | `#5f5e5a` |

Arrow colours:
- Inter-layer solid: stroke `#5f5e5a`
- Intra-ingestion: stroke `#0f6e56`
- Intra-generation: stroke `#185fa5`
- Dashed (config/reference): stroke `#b4b2a9`, `stroke-dasharray="4 3"`

---

## Arrow routing rules — CRITICAL

**The rule that prevents box-crossing bugs:**
> Plan and verify EVERY arrow route against box boundary coordinates BEFORE writing any SVG.
> Write out each segment as (x1,y1)→(x2,y2) and confirm it doesn't enter any box interior.

### Gap corridor routing
All cross-column arrows route through the gap corridor (x=350..430).
Use distinct x offsets within the corridor to avoid lines overlapping:

| Arrow | Corridor x |
|---|---|
| scripts → retrieval | x=375 |
| scripts → ingestion | x=383 |
| eval → generation (dashed) | x=393 |
| config → retrieval (dashed) | x=380 |
| config → evaluation (dashed) | x=390 |

### Verified arrow routes (current)
```
config → ingestion:    diagonal (310,60)→(195,90)
config → retrieval:    (340,60)→(380,60)→(380,272)→(195,272)→(195,280)
config → evaluation:   (350,60)→(390,60)→(390,482)→(350,482)
config → generation:   diagonal (450,60)→(595,280)
config → scripts:      diagonal (465,60)→(595,490)
ingestion → retrieval: straight down (195,260)→(195,280)   [20px gap]
retrieval → generation: straight across (350,350)→(430,350) [80px gap]
scripts → generation:  straight up (672,490)→(672,472)      [20px gap]
run_eval → eval:       straight left (444,608)→(352,608)
scripts → ingestion:   (430,546)→(383,546)→(383,82)→(195,82)→(195,90)
scripts → retrieval:   (430,640)→(375,640)→(375,273)→(195,273)→(195,280)
eval → generation:     (350,560)→(393,560)→(393,350)→(430,350)
env bar → config:      straight up (400,752)→(400,62)
```

---

## How to add a new component

### Adding a new box inside an existing layer
1. Check available space inside the outer layer rect
2. Assign x/y so it doesn't overlap siblings
3. If the outer rect is too short, increase its height and shift everything below it down
4. Update any arrow y-coordinates that referenced the old positions
5. Verify the legend still fits; extend viewBox height if needed

### Adding a new layer (e.g. frontend)
1. Decide: new row (extend canvas height) or new column (rare — layout is already two-col)
2. Assign y range with ~20px gap above and below adjacent layers
3. Pick a colour from the palette or add a new entry
4. Plan ALL arrows to/from the new layer through the gap corridor before writing
5. Add a legend entry
6. Update viewBox height

### Adding a frontend layer (planned)
Suggested position: new row above Scripts/Evaluation, or a third column.
Most natural: a new `FRONTEND` row at col B alongside a new `src/api/` box at col A,
both sitting between generation (y=280..470) and the current scripts/eval rows.
This would require shifting scripts/eval/env/docs bars down by ~100px.

---

## Markers (defined in `<defs>`)
```xml
<marker id="arr" ...>       <!-- general inter-layer, stroke #5f5e5a -->
<marker id="arr-teal" ...>  <!-- ingestion internal, stroke #0f6e56  -->
<marker id="arr-blue" ...>  <!-- generation internal, stroke #185fa5 -->
```

---

## How to invoke this skill (Claude Code)
```
read .claude/skills/diagram-update.md then [describe what to add/change]
```

Examples:
```
read .claude/skills/diagram-update.md then add a frontend layer and a src/api/ FastAPI box
read .claude/skills/diagram-update.md then add a reranker.py box inside the retrieval layer
read .claude/skills/diagram-update.md then update the generation layer to show a new model
```
