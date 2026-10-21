# Work-IQ: Autonomous Offline Agent & Knowledge Graph Studio

> **An offline-first autonomous agent ecosystem combining an interactive Knowledge Graph, Code Studio with automated test runner, Obsidian curriculum synthesis, AI study tutor, and agent fleet telemetry.**

---

## 🌟 Key Capabilities

### 1. Interactive Knowledge Graph Studio
* **Bespoke Canvas Physics Engine**: Real-time force-directed topology visualizer with degree-weighted node sizing, halo effects, and velocity dampening.
* **Distinct Semantic Hierarchy**: Distinct color-coded nodes for Curricula (Indigo), Notes (Slate), Tasks (Rose), Distilled Facts (Emerald), Workspace Projects (Electric Cyan `#00f2fe`), and Workspace Files (Teal `#14b8a6`).
* **Relational Node Linking**: Interactive linking modal allowing bidirectional connections (`implements`, `references`, `tests`, `studied_from`, `depends_on`, `extends`) between code files, notes, and concept nodes.
* **Topic Isolation & Search**: Instant autocomplete search and one-click topic highlighting that isolates specific learning paths on the canvas.

### 2. Code Studio & Workspace Engineering
* **Multi-Workspace Explorer**: Inspect and manage projects generated autonomously by agents in `data/workspaces/`.
* **Integrated Source Code Editor**: In-browser code editing with dirty state indicators and <kbd>Ctrl</kbd>+<kbd>S</kbd> save shortcut with automated AST re-indexing.
* **Offline Execution Terminal**: Subprocess runner executing `pytest -v` or `python <script>` with real-time ANSI coloring, status badges, and sub-second execution duration metrics.
* **Offline / Online Toggle**: Switch between 100% offline local inference (Ollama `qwen2.5-coder:3b`/`7b`, `llama3.1`) and cloud models.
* **Autonomous Coding Assistant**: Natural language prompt bar that generates Python implementations, unit tests, and immediately links them into the Knowledge Graph.

### 3. Curriculum Architecture Engine & Obsidian Vault Integration
* Synthesizes atomic, interconnected technical curricula across any computer science domain.
* Automatically writes markdown notes into your Obsidian Vault (`OBSIDIAN_VAULT`), linking concepts with standard `[[wiki-links]]`.

### 4. Grounded AI Study Tutor
* Chat interface grounded in local vault notes and graph memory.
* Answers questions with source node citations, mathematical formatting, and code snippets.

### 5. Agent Fleet Telemetry Dashboard
* **Telemetry KPIs**: Real-time tracking of total agent tasks, clean success rates, tool call counts, orchestrated subtasks, distilled insights, and average execution runtime.
* **Tool Frequency Analytics**: Visual breakdown of agent tool usage (`bash`, `python_ast`, `obsidian_search`, `write_note`, etc.).
* **Step-by-Step Execution Traces**: Interactive slide-out drawer inspecting complete agent thought chains, tool arguments, and stdout observations.

---

## 📂 Repository Structure

```text
Work-IQ/
├── offline-agent/
│   ├── agent/                 # Autonomous agent loop, LLM adapters (Ollama), prompt templates
│   ├── data/
│   │   ├── memory.db          # SQLite persistent memory (nodes, edges, tasks, telemetry)
│   │   └── workspaces/        # Agent-generated workspaces and test suites (e.g. my_project)
│   ├── eval/                  # Agent benchmark and evaluation harness
│   ├── memory/
│   │   ├── db.py              # SQLite storage layer with WAL mode
│   │   ├── graph.py           # AST parser, workspace indexing, and hybrid graph search
│   │   └── obsidian.py        # Vault crawler and markdown wiki-link indexer
│   ├── tests/                 # Unit and integration test suites
│   ├── tools/                 # Agent tools (filesystem, terminal, search, code inspection)
│   ├── ui/
│   │   ├── app.js             # Client-side graph canvas, Code Studio, and dashboard controller
│   │   ├── index.html         # Single-page studio interface
│   │   ├── server.py          # Zero-dependency Python HTTP API server
│   │   └── styles.css         # Glassmorphic dark / light design system
│   ├── main.py                # CLI runner for autonomous agent tasks
│   ├── study.py               # Curriculum planner and graph query engine
│   └── requirements.txt       # Python dependencies
├── plan.md                    # Technical roadmap and phase implementation documentation
└── README.md                  # Project overview and documentation
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
* Python 3.10+ (tested on Python 3.12, 3.13, and 3.14)
* *(Optional for local AI)* [Ollama](https://ollama.ai/) installed with local models:
  ```bash
  ollama pull qwen2.5-coder:3b
  ollama pull llama3.1:latest
  ```

### 2. Installation
```bash
git clone https://github.com/ej2k4/Work-IQ.git
cd Work-IQ/offline-agent

# Set up virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Launching the Studio Server
```bash
python ui/server.py 8000
```
Open your browser to:
👉 **`http://localhost:8000/`**

---

## ⌨️ Code Studio Shortcuts & Features

| Action | Control |
| :--- | :--- |
| **Run Pytest Suite** | Click **Run Tests** in the toolbar or select `pytest` in the terminal |
| **Save Code File** | Click **Save File** or press <kbd>Ctrl</kbd>+<kbd>S</kbd> / <kbd>Cmd</kbd>+<kbd>S</kbd> |
| **Connect Graph Node** | Click **+ Link** in the file sidebar to link with any concept or note |
| **Focus in Graph** | Click **View in Graph** in Code Studio to navigate to the project hub |
| **Toggle Theme** | Click the **Dark / Light** button in the top header |
| **Inspect Telemetry Trace** | Click any task row in the Agent Dashboard table |

---

## 📄 License
MIT License. Built for offline-first autonomous agent engineering and knowledge distillation.
