# Hermes Memory Control

A desktop control panel for the [Hermes](https://github.com/b7216309-jpg/hermes-consolidating-local-memory) **consolidating-local-memory** plugin. Browse, edit, and visualize your agent's consolidated memory database in real-time.

Built with Electron, Three.js, and a direct WSL bridge to the SQLite database.

![Dashboard](screenshots/dashboard.png)

---

## Features

### Dashboard
Live stats from your memory database — active facts, topics, sessions, preferences, contradictions, last consolidation timestamp.

### DB Explorer
Full table views for every entity type with search, category filters, and inline editing:
- **Facts** — search, filter by category, toggle inactive, click to edit/deactivate/delete
- **Topics** — cluster view with fact counts, edit titles and summaries
- **Sessions** — chronological session history with summaries
- **Preferences & Policies** — manage behavioral directives
- **Contradictions** — supersession history with winner/loser context

![Facts Explorer](screenshots/facts.png)

### Inline Editing
Click any row to open the detail panel — edit content, category, importance, and more. Save, deactivate, or delete directly.

![Editing](screenshots/editing.png)

### 3D Memory Graph
Interactive force-directed graph powered by Three.js:
- **Topics** as violet octahedrons, **Facts** as orange spheres, **Preferences** as amber cubes
- Node size scales with importance, opacity with salience
- Contradiction edges highlighted in red
- Text labels on every node
- Click to filter by type (topics / facts / preferences / edges)
- Orbit, zoom, and click-to-inspect

![3D Graph](screenshots/graph3d.png)

### Wiki Viewer
Browse the compiled markdown wiki exported by the plugin — rendered in-app with internal link navigation.

![Wiki](screenshots/wiki.png)

### Config Editor
Edit all 30+ plugin configuration keys organized in tabs:
- Consolidation gates, topic clustering, pruning
- Retrieval backend, extraction mode
- Snapshot sync settings
- Wiki export options
- LLM & embedding backend
- Salience decay & spaced review

![Config](screenshots/config.png)

### Themes
Four color themes matching the Gruvbox/Nord/Forest/Ember palette family. JetBrains Mono throughout.

---

## Architecture

```
Electron Main Process
  ├── IPC: load-config / save-config  →  reads/writes config.yaml via js-yaml
  ├── IPC: db-query                   →  WSL bridge (python3 → SQLite)
  │     copies db_query.py to temp, runs via:
  │     wsl -e python3 /mnt/c/.../hmc_db_query.py <db_path> <query_type> <args_file>
  └── IPC: window controls, file picker

Renderer (contextIsolation: false, nodeIntegration: true)
  ├── core.js      — nav, dashboard, tables, config form, editable detail panel
  ├── graph3d.js   — Three.js scene, force simulation, sprite labels, filter toggles
  └── wiki.js      — marked.js markdown rendering, internal link navigation
```

The app communicates with the SQLite database through a universal Python query script (`db_query.py`) executed via WSL. This supports 10+ query types including full CRUD operations.

---

## Requirements

- **Windows 10/11** with **WSL** (Ubuntu or similar)
- **Python 3.10+** installed in WSL with `sqlite3` module
- **Node.js 18+** and **npm**
- The [Hermes](https://github.com/b7216309-jpg/hermes-consolidating-local-memory) agent with the consolidating-local-memory plugin configured

---

## Install

```bash
git clone https://github.com/b7216309-jpg/HermesMemoryControl.git
cd HermesMemoryControl
npm install
```

## Run

```bash
npm start
```

Then click **...** to browse to your Hermes home directory (e.g. `\\wsl$\Ubuntu\home\user\.hermes`) and hit **CONNECT**.

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Desktop | Electron 35 |
| 3D | Three.js 0.183 |
| Markdown | marked 18 |
| Config | js-yaml 4 |
| DB Bridge | Python 3 + sqlite3 via WSL |
| Font | JetBrains Mono |

---

## License

MIT
