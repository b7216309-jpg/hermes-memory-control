/* ── Mock data for demo/screenshot mode ── */
'use strict';

const MOCK_STATS = {
  active_facts: 247,
  inactive_facts: 89,
  topics: 43,
  sessions: 31,
  preferences: 18,
  policies: 5,
  summaries: 31,
  journals: 8,
  history_rows: 1847,
  contradictions: 12,
  last_consolidation: '2026-04-07 14:32',
};

const MOCK_FACTS = {
  facts: [
    { id: 1, content: 'User is a native French speaker from Quebec, communicates in English for technical work', category: 'user_pref', subject_key: 'user.language', value_key: 'french_native', importance: 9, confidence: 0.95, salience: 0.91, exclusive: 1, polarity: '', active: 1, source: 'conversation', source_session_id: 's-001', created_at_str: '2026-03-12 09:14', updated_at_str: '2026-04-06 18:20', topic: 'Personal Identity' },
    { id: 2, content: 'Runs Ubuntu 22.04 under WSL2 on Windows 11 as primary dev environment', category: 'environment', subject_key: 'dev.os', value_key: 'wsl2_ubuntu', importance: 8, confidence: 0.98, salience: 0.88, exclusive: 1, polarity: '', active: 1, source: 'conversation', source_session_id: 's-002', created_at_str: '2026-03-12 10:30', updated_at_str: '2026-04-05 11:45', topic: 'Development Environment' },
    { id: 3, content: 'Building Hermes, an MCP-based memory consolidation plugin for Claude', category: 'project', subject_key: 'project.hermes', value_key: 'mcp_memory_plugin', importance: 10, confidence: 0.99, salience: 0.95, exclusive: 0, polarity: '', active: 1, source: 'conversation', source_session_id: 's-001', created_at_str: '2026-03-10 14:00', updated_at_str: '2026-04-07 09:12', topic: 'Hermes Memory Plugin' },
    { id: 4, content: 'Has an NVIDIA RTX 4070 Ti used for local LLM inference and gaming', category: 'environment', subject_key: 'hardware.gpu', value_key: 'rtx_4070ti', importance: 7, confidence: 0.97, salience: 0.72, exclusive: 1, polarity: '', active: 1, source: 'conversation', source_session_id: 's-003', created_at_str: '2026-03-15 20:10', updated_at_str: '2026-04-01 16:30', topic: 'Hardware Setup' },
    { id: 5, content: 'Enjoys welding as a hobby, builds custom metal furniture and art pieces', category: 'general', subject_key: 'hobby.welding', value_key: 'metalwork', importance: 6, confidence: 0.90, salience: 0.65, exclusive: 0, polarity: '', active: 1, source: 'conversation', source_session_id: 's-004', created_at_str: '2026-03-18 12:45', updated_at_str: '2026-03-28 14:20', topic: 'Personal Identity' },
    { id: 6, content: 'Prefers concise, no-fluff responses with inline code comments over separate docs', category: 'user_pref', subject_key: 'pref.response_style', value_key: 'concise', importance: 8, confidence: 0.92, salience: 0.84, exclusive: 1, polarity: '', active: 1, source: 'conversation', source_session_id: 's-002', created_at_str: '2026-03-13 08:22', updated_at_str: '2026-04-04 10:15', topic: 'Communication Style' },
    { id: 7, content: 'Plays Satisfactory, Factorio, and Dyson Sphere Program regularly', category: 'general', subject_key: 'gaming.favorites', value_key: 'factory_builders', importance: 5, confidence: 0.88, salience: 0.58, exclusive: 0, polarity: '', active: 1, source: 'conversation', source_session_id: 's-005', created_at_str: '2026-03-20 21:30', updated_at_str: '2026-04-03 19:45', topic: 'Gaming Interests' },
    { id: 8, content: 'Uses Python 3.12 with SQLite for Hermes backend, Electron for the control panel', category: 'project', subject_key: 'project.hermes.stack', value_key: 'python_sqlite_electron', importance: 8, confidence: 0.96, salience: 0.80, exclusive: 0, polarity: '', active: 1, source: 'conversation', source_session_id: 's-006', created_at_str: '2026-03-22 15:00', updated_at_str: '2026-04-06 13:40', topic: 'Hermes Memory Plugin' },
    { id: 9, content: 'Works as a senior developer at a mid-size SaaS company, remote position', category: 'workflow', subject_key: 'work.role', value_key: 'senior_dev_remote', importance: 7, confidence: 0.85, salience: 0.70, exclusive: 1, polarity: '', active: 1, source: 'conversation', source_session_id: 's-003', created_at_str: '2026-03-16 09:00', updated_at_str: '2026-03-30 11:20', topic: 'Work & Career' },
    { id: 10, content: 'Experimenting with local Mistral and Llama models via Ollama for embedding generation', category: 'project', subject_key: 'llm.local_inference', value_key: 'ollama_mistral_llama', importance: 7, confidence: 0.91, salience: 0.76, exclusive: 0, polarity: '', active: 1, source: 'conversation', source_session_id: 's-007', created_at_str: '2026-03-25 17:15', updated_at_str: '2026-04-05 20:30', topic: 'AI & LLM Projects' },
    { id: 11, content: 'Prefers dark themes in all editors and tools, uses Gruvbox color scheme', category: 'user_pref', subject_key: 'pref.theme', value_key: 'dark_gruvbox', importance: 5, confidence: 0.94, salience: 0.62, exclusive: 1, polarity: '', active: 1, source: 'conversation', source_session_id: 's-004', created_at_str: '2026-03-19 10:30', updated_at_str: '2026-04-02 08:15', topic: 'Development Environment' },
    { id: 12, content: 'Uses neovim with custom Lua config as primary editor, VS Code as fallback', category: 'environment', subject_key: 'dev.editor', value_key: 'neovim_lua', importance: 6, confidence: 0.93, salience: 0.68, exclusive: 1, polarity: '', active: 1, source: 'conversation', source_session_id: 's-002', created_at_str: '2026-03-14 11:00', updated_at_str: '2026-04-03 14:50', topic: 'Development Environment' },
  ],
};

const MOCK_TOPICS = {
  topics: [
    { id: 1, slug: 'personal-identity', title: 'Personal Identity', category: 'general', fact_count: 8, summary: 'Core personal details: native French speaker from Quebec, enjoys welding and metalwork as creative outlet, values direct communication.', importance: 9, salience: 0.88, updated_at_str: '2026-04-06 18:20' },
    { id: 2, slug: 'development-environment', title: 'Development Environment', category: 'environment', fact_count: 12, summary: 'Primary setup: WSL2 Ubuntu 22.04 on Windows 11, neovim with Lua config, Gruvbox theme, Python 3.12, extensive CLI tooling.', importance: 8, salience: 0.85, updated_at_str: '2026-04-05 11:45' },
    { id: 3, slug: 'ai-llm-projects', title: 'AI & LLM Projects', category: 'project', fact_count: 15, summary: 'Active exploration of local LLM inference with Ollama, embedding generation experiments, prompt engineering for memory systems.', importance: 8, salience: 0.82, updated_at_str: '2026-04-05 20:30' },
    { id: 4, slug: 'gaming-interests', title: 'Gaming Interests', category: 'general', fact_count: 6, summary: 'Strong preference for factory/automation games: Satisfactory, Factorio, Dyson Sphere Program. Occasional FPS and strategy titles.', importance: 5, salience: 0.55, updated_at_str: '2026-04-03 19:45' },
    { id: 5, slug: 'hermes-memory-plugin', title: 'Hermes Memory Plugin', category: 'project', fact_count: 22, summary: 'MCP-based memory consolidation plugin for Claude. Python/SQLite backend, Electron control panel. Spaced repetition review, wiki export, graph visualization.', importance: 10, salience: 0.95, updated_at_str: '2026-04-07 09:12' },
    { id: 6, slug: 'work-career', title: 'Work & Career', category: 'workflow', fact_count: 5, summary: 'Senior developer at mid-size SaaS company, fully remote. Focus on backend services and infrastructure.', importance: 7, salience: 0.68, updated_at_str: '2026-03-30 11:20' },
    { id: 7, slug: 'communication-style', title: 'Communication Style', category: 'user_pref', fact_count: 4, summary: 'Prefers concise technical responses, inline comments over separate documentation, minimal verbosity.', importance: 8, salience: 0.80, updated_at_str: '2026-04-04 10:15' },
    { id: 8, slug: 'hardware-setup', title: 'Hardware Setup', category: 'environment', fact_count: 7, summary: 'RTX 4070 Ti GPU, 32GB RAM, dual monitor setup. Used for local LLM inference, gaming, and development.', importance: 7, salience: 0.70, updated_at_str: '2026-04-01 16:30' },
  ],
};

const MOCK_SESSIONS = {
  sessions: [
    { session_id: 'ses-20260407-a1b2', status: 'open', label: 'Hermes control panel polish', summary: 'Working on the Electron control panel for Hermes. Added 3D graph visualization, wiki viewer, and dark theme refinements. Fixed config save/load for WSL paths.', started_at_str: '2026-04-07 09:00', ended_at_str: '', last_activity_str: '2026-04-07 14:32' },
    { session_id: 'ses-20260406-c3d4', status: 'closed', label: 'Memory consolidation tuning', summary: 'Tuned consolidation parameters: adjusted decay half-life to 90 days, set minimum salience threshold to 0.15. Ran benchmark against LongMemEval dataset.', started_at_str: '2026-04-06 10:15', ended_at_str: '2026-04-06 17:45', last_activity_str: '2026-04-06 17:45' },
    { session_id: 'ses-20260405-e5f6', status: 'closed', label: 'Wiki export implementation', summary: 'Implemented wiki export feature: markdown generation from topics and sessions, directory structure with index, cross-linking between pages.', started_at_str: '2026-04-05 14:00', ended_at_str: '2026-04-05 19:30', last_activity_str: '2026-04-05 19:30' },
    { session_id: 'ses-20260403-g7h8', status: 'closed', label: 'Embedding and retrieval experiments', summary: 'Tested FTS vs hybrid retrieval backends. Hybrid showed 12% better recall on personal facts. Configured Ollama embedding endpoint for local inference.', started_at_str: '2026-04-03 11:00', ended_at_str: '2026-04-03 16:20', last_activity_str: '2026-04-03 16:20' },
    { session_id: 'ses-20260401-i9j0', status: 'closed', label: 'Welding project brainstorm', summary: 'Discussed design ideas for a custom steel bookshelf with integrated LED lighting. Sketched joint details and material list for 2-inch square tubing frame.', started_at_str: '2026-04-01 19:00', ended_at_str: '2026-04-01 20:15', last_activity_str: '2026-04-01 20:15' },
    { session_id: 'ses-20260330-k1l2', status: 'closed', label: 'Satisfactory megabase planning', summary: 'Planned nuclear power layout and turbofuel production chain for Satisfactory megabase. Calculated ratios for 20 GW target output.', started_at_str: '2026-03-30 20:00', ended_at_str: '2026-03-30 22:30', last_activity_str: '2026-03-30 22:30' },
  ],
};

const MOCK_PREFERENCES = {
  preferences: [
    { id: 1, preference_key: 'response_style', label: 'Response Style', value: 'concise', content: 'Keep responses concise and direct. Avoid unnecessary preamble, filler phrases, and verbose explanations. Get to the point.', importance: 9, salience: 0.90, updated_at_str: '2026-04-04 10:15' },
    { id: 2, preference_key: 'code_style', label: 'Code Style', value: 'clean_minimal', content: 'Write clean, minimal code. Prefer readability over cleverness. Use descriptive variable names but avoid over-engineering.', importance: 8, salience: 0.85, updated_at_str: '2026-04-02 14:30' },
    { id: 3, preference_key: 'language', label: 'Language Preference', value: 'french_native', content: 'User is native French speaker. Use English for all technical communication but understand French context and idioms.', importance: 7, salience: 0.78, updated_at_str: '2026-03-28 09:00' },
    { id: 4, preference_key: 'theme', label: 'Visual Theme', value: 'dark', content: 'Always prefer dark themes and color schemes. Gruvbox is the preferred palette for code and UI elements.', importance: 5, salience: 0.60, updated_at_str: '2026-03-25 16:45' },
    { id: 5, preference_key: 'documentation', label: 'Documentation Style', value: 'inline_comments', content: 'Prefer inline code comments over separate documentation files. Keep README minimal. Document complex logic at point of use.', importance: 7, salience: 0.75, updated_at_str: '2026-04-01 11:20' },
  ],
};

const MOCK_POLICIES = {
  policies: [
    { id: 1, policy_key: 'skill_review', label: 'Spaced Repetition Review', content: 'Review facts using spaced repetition intervals: 1, 3, 7, 14, 30 days. Prioritize high-importance facts with decaying salience for review scheduling.', importance: 8, salience: 0.82, updated_at_str: '2026-04-06 12:00' },
    { id: 2, policy_key: 'memory_consolidation', label: 'Memory Consolidation Policy', content: 'Run consolidation after minimum 5 sessions or 24 hours since last run. Merge duplicate facts, resolve contradictions by preferring newer information with higher confidence.', importance: 9, salience: 0.90, updated_at_str: '2026-04-07 09:12' },
    { id: 3, policy_key: 'conversation_flow', label: 'Conversation Flow', content: 'Do not repeat information the user already knows. Reference prior context naturally. Ask clarifying questions only when truly ambiguous.', importance: 7, salience: 0.75, updated_at_str: '2026-04-03 15:30' },
  ],
};

const MOCK_CONTRADICTIONS = {
  contradictions: [
    { id: 1, subject_key: 'gaming.favorites', resolution: 'superseded', winner_content: 'Plays Satisfactory, Factorio, and Dyson Sphere Program regularly', loser_content: 'Mainly plays Factorio and Rimworld', created_at_str: '2026-04-03 19:45' },
    { id: 2, subject_key: 'project.focus', resolution: 'superseded', winner_content: 'Primary project is Hermes memory consolidation plugin with MCP integration', loser_content: 'Working on a generic Claude tool framework', created_at_str: '2026-03-28 10:00' },
    { id: 3, subject_key: 'pref.response_style', resolution: 'refined', winner_content: 'Prefers concise responses with inline code comments', loser_content: 'Likes detailed explanations with step-by-step breakdowns', created_at_str: '2026-04-04 10:15' },
    { id: 4, subject_key: 'user.location', resolution: 'superseded', winner_content: 'Based in Quebec, Canada, working remotely', loser_content: 'Located in Montreal area', created_at_str: '2026-03-30 14:20' },
  ],
};

/* ── Graph data ── */
function buildMockGraph() {
  const nodes = [];
  const edges = [];
  let nodeId = 1;

  // Topic nodes
  const topicNodes = MOCK_TOPICS.topics.map(t => {
    const n = { id: `t-${t.id}`, type: 'topic', label: t.title, category: t.category, importance: t.importance, salience: t.salience, subject_key: t.slug };
    nodes.push(n);
    return n;
  });

  // Preference nodes
  MOCK_PREFERENCES.preferences.forEach(p => {
    nodes.push({ id: `p-${p.id}`, type: 'preference', label: p.label, category: 'user_pref', importance: p.importance, salience: p.salience, subject_key: p.preference_key });
  });

  // Fact nodes (a curated subset for visual appeal)
  const factSubset = [
    { id: 'f-1', type: 'fact', label: 'French speaker from Quebec', category: 'user_pref', importance: 9, salience: 0.91, subject_key: 'user.language', topic_id: 1 },
    { id: 'f-2', type: 'fact', label: 'WSL2 Ubuntu 22.04', category: 'environment', importance: 8, salience: 0.88, subject_key: 'dev.os', topic_id: 2 },
    { id: 'f-3', type: 'fact', label: 'Hermes MCP memory plugin', category: 'project', importance: 10, salience: 0.95, subject_key: 'project.hermes', topic_id: 5 },
    { id: 'f-4', type: 'fact', label: 'RTX 4070 Ti GPU', category: 'environment', importance: 7, salience: 0.72, subject_key: 'hardware.gpu', topic_id: 8 },
    { id: 'f-5', type: 'fact', label: 'Welding & metalwork hobby', category: 'general', importance: 6, salience: 0.65, subject_key: 'hobby.welding', topic_id: 1 },
    { id: 'f-6', type: 'fact', label: 'Concise response style', category: 'user_pref', importance: 8, salience: 0.84, subject_key: 'pref.response_style', topic_id: 7 },
    { id: 'f-7', type: 'fact', label: 'Satisfactory & Factorio', category: 'general', importance: 5, salience: 0.58, subject_key: 'gaming.favorites', topic_id: 4 },
    { id: 'f-8', type: 'fact', label: 'Python/SQLite/Electron stack', category: 'project', importance: 8, salience: 0.80, subject_key: 'project.hermes.stack', topic_id: 5 },
    { id: 'f-9', type: 'fact', label: 'Senior dev, remote SaaS', category: 'workflow', importance: 7, salience: 0.70, subject_key: 'work.role', topic_id: 6 },
    { id: 'f-10', type: 'fact', label: 'Ollama local inference', category: 'project', importance: 7, salience: 0.76, subject_key: 'llm.local_inference', topic_id: 3 },
    { id: 'f-11', type: 'fact', label: 'Gruvbox dark theme', category: 'user_pref', importance: 5, salience: 0.62, subject_key: 'pref.theme', topic_id: 2 },
    { id: 'f-12', type: 'fact', label: 'Neovim with Lua config', category: 'environment', importance: 6, salience: 0.68, subject_key: 'dev.editor', topic_id: 2 },
    { id: 'f-13', type: 'fact', label: 'Spaced repetition review', category: 'project', importance: 8, salience: 0.78, subject_key: 'hermes.review', topic_id: 5 },
    { id: 'f-14', type: 'fact', label: '32GB RAM dual monitor', category: 'environment', importance: 6, salience: 0.64, subject_key: 'hardware.ram', topic_id: 8 },
    { id: 'f-15', type: 'fact', label: 'Wiki export feature', category: 'project', importance: 7, salience: 0.74, subject_key: 'hermes.wiki', topic_id: 5 },
    { id: 'f-16', type: 'fact', label: 'Prompt engineering focus', category: 'project', importance: 7, salience: 0.72, subject_key: 'ai.prompts', topic_id: 3 },
    { id: 'f-17', type: 'fact', label: 'Custom steel bookshelf', category: 'general', importance: 4, salience: 0.45, subject_key: 'welding.current', topic_id: 1 },
    { id: 'f-18', type: 'fact', label: 'Nuclear power in Satisfactory', category: 'general', importance: 3, salience: 0.40, subject_key: 'gaming.satisfactory', topic_id: 4 },
    { id: 'f-19', type: 'fact', label: 'FTS vs hybrid retrieval', category: 'project', importance: 8, salience: 0.82, subject_key: 'hermes.retrieval', topic_id: 5 },
    { id: 'f-20', type: 'fact', label: 'Backend services focus at work', category: 'workflow', importance: 6, salience: 0.60, subject_key: 'work.focus', topic_id: 6 },
    { id: 'f-21', type: 'fact', label: 'Minimal README preference', category: 'user_pref', importance: 6, salience: 0.58, subject_key: 'pref.docs', topic_id: 7 },
    { id: 'f-22', type: 'fact', label: 'Decay half-life 90 days', category: 'project', importance: 7, salience: 0.70, subject_key: 'hermes.decay', topic_id: 5 },
    { id: 'f-23', type: 'fact', label: 'Mistral & Llama models', category: 'project', importance: 6, salience: 0.66, subject_key: 'llm.models', topic_id: 3 },
    { id: 'f-24', type: 'fact', label: 'Dyson Sphere Program', category: 'general', importance: 4, salience: 0.48, subject_key: 'gaming.dsp', topic_id: 4 },
    { id: 'f-25', type: 'fact', label: 'CLI tooling enthusiast', category: 'environment', importance: 5, salience: 0.55, subject_key: 'dev.cli', topic_id: 2 },
  ];
  factSubset.forEach(f => nodes.push(f));

  // Topic membership edges (fact -> topic)
  const topicIdMap = { 1: 't-1', 2: 't-2', 3: 't-3', 4: 't-4', 5: 't-5', 6: 't-6', 7: 't-7', 8: 't-8' };
  factSubset.forEach(f => {
    if (f.topic_id && topicIdMap[f.topic_id]) {
      edges.push({ source: f.id, target: topicIdMap[f.topic_id], type: 'topic_membership' });
    }
  });

  // Preference -> topic edges
  edges.push({ source: 'p-1', target: 't-7', type: 'topic_membership' });
  edges.push({ source: 'p-2', target: 't-2', type: 'topic_membership' });
  edges.push({ source: 'p-3', target: 't-1', type: 'topic_membership' });
  edges.push({ source: 'p-4', target: 't-2', type: 'topic_membership' });
  edges.push({ source: 'p-5', target: 't-7', type: 'topic_membership' });

  // Contradiction edges
  edges.push({ source: 'f-7', target: 'f-18', type: 'contradicts' });
  edges.push({ source: 'f-6', target: 'f-21', type: 'contradicts' });

  return { nodes, edges };
}

const MOCK_GRAPH = buildMockGraph();

/* ── Wiki data ── */
const MOCK_WIKI_LIST = {
  files: [
    'index.md',
    'topics/personal.md',
    'topics/development.md',
    'topics/gaming.md',
    'sessions/latest.md',
    'preferences.md',
  ],
};

const MOCK_WIKI_PAGES = {
  'index.md': `# Hermes Memory Wiki

> Auto-generated knowledge base from consolidated memory

## Overview

| Metric | Count |
|--------|-------|
| Active facts | 247 |
| Topics | 43 |
| Sessions | 31 |
| Preferences | 18 |

## Topics

- [Personal Identity](topics/personal.md) -- core personal details and hobbies
- [Development Environment](topics/development.md) -- tools, OS, and workflow
- [Gaming Interests](topics/gaming.md) -- games and gaming preferences

## Recent Activity

Last consolidation: **2026-04-07 14:32**

---
*Generated by Hermes Memory Plugin v0.9*`,

  'topics/personal.md': `# Personal Identity

## Core Facts

- **Language**: Native French speaker from Quebec, uses English for technical work
- **Hobbies**: Welding and metalwork -- builds custom steel furniture and art pieces
- **Location**: Based in Quebec, Canada
- **Work**: Senior developer at a mid-size SaaS company (remote)

## Current Projects

Building a custom steel bookshelf with integrated LED lighting. Using 2-inch square tubing for the frame.

## Communication

Prefers direct, concise communication. Values clarity over politeness padding. Understands both French and English idioms.

## Related Topics

- [Development Environment](development.md)
- [Preferences](../preferences.md)

---
*Last updated: 2026-04-06 18:20*`,

  'topics/development.md': `# Development Environment

## Operating System

- **Primary**: Ubuntu 22.04 under WSL2 on Windows 11
- **Shell**: zsh with custom aliases
- **Terminal**: Windows Terminal with Gruvbox theme

## Editor

- **Primary**: Neovim with custom Lua configuration
- **Fallback**: VS Code for complex debugging sessions
- **Theme**: Gruvbox Dark across all tools

## Languages & Tools

| Language | Usage |
|----------|-------|
| Python 3.12 | Backend, scripts, Hermes plugin |
| JavaScript | Electron apps, web tooling |
| Bash/Zsh | Automation, CLI tools |
| SQL | SQLite for Hermes data layer |

## Hardware

- **GPU**: NVIDIA RTX 4070 Ti
- **RAM**: 32GB DDR5
- **Monitors**: Dual setup

## Key Tools

- Ollama for local LLM inference
- Git with conventional commits
- Docker for service isolation
- ripgrep, fzf, tmux

---
*Last updated: 2026-04-05 11:45*`,

  'topics/gaming.md': `# Gaming Interests

## Favorite Genres

Factory/automation builders are the primary interest.

## Active Games

1. **Satisfactory** -- currently planning a nuclear power megabase (20 GW target)
2. **Factorio** -- long-time player, megabase experience
3. **Dyson Sphere Program** -- interstellar logistics phase

## Play Style

- Optimization-focused: enjoys calculating production ratios
- Prefers long-term base building over speedruns
- Plays on PC with RTX 4070 Ti

## Related

- [Hardware Setup](../topics/development.md#hardware)

---
*Last updated: 2026-04-03 19:45*`,

  'sessions/latest.md': `# Session: Hermes Control Panel Polish

**ID**: ses-20260407-a1b2
**Status**: open
**Started**: 2026-04-07 09:00

## Summary

Working on the Electron control panel for Hermes. Key accomplishments this session:

- Added 3D force-directed graph visualization using Three.js
- Implemented wiki viewer with markdown rendering
- Dark theme refinements across all views
- Fixed config save/load for WSL UNC paths
- Tuned graph physics: repulsion, attraction, and damping parameters

## Facts Extracted

- Hermes control panel uses Electron with no-framework vanilla JS
- Graph visualization uses Three.js with custom orbit controls
- Wiki viewer renders markdown with internal link navigation

## Previous Session

Memory consolidation tuning (2026-04-06) -- adjusted decay parameters and ran LongMemEval benchmark.

---
*Last activity: 2026-04-07 14:32*`,

  'preferences.md': `# User Preferences

## Communication

| Key | Value | Detail |
|-----|-------|--------|
| response_style | concise | No fluff, get to the point |
| documentation | inline_comments | Prefer comments at point of use |

## Code

| Key | Value | Detail |
|-----|-------|--------|
| code_style | clean_minimal | Readable over clever |
| language | french_native | English for technical work |

## Visual

| Key | Value | Detail |
|-----|-------|--------|
| theme | dark | Gruvbox preferred palette |

## Policies

1. **Spaced Repetition**: Review facts at intervals of 1, 3, 7, 14, 30 days
2. **Memory Consolidation**: Run after 5+ sessions or 24h since last run
3. **Conversation Flow**: Don't repeat known context, ask only when truly ambiguous

---
*Last updated: 2026-04-04 10:15*`,
};

/* ── Demo config ── */
const MOCK_CONFIG = {
  config: {
    db_path: '$HERMES_HOME/consolidating_memory.db',
    min_hours: 24,
    min_sessions: 5,
    scan_cooldown_seconds: 600,
    prefetch_limit: 8,
    max_topic_facts: 5,
    topic_summary_chars: 650,
    session_summary_chars: 900,
    prune_after_days: 90,
    episode_body_retention_hours: 24,
    decay_half_life_days: 90,
    decay_min_salience: 0.15,
    reconsolidation_window_hours: 6,
    review_intervals_days: '1,3,7,14,30',
    builtin_snapshot_sync_enabled: true,
    builtin_memory_dir: '$HERMES_HOME/memories',
    builtin_snapshot_user_chars: 1375,
    builtin_snapshot_memory_chars: 2200,
    wiki_export_enabled: true,
    wiki_export_dir: '$HERMES_HOME/consolidating_memory_wiki',
    wiki_export_on_consolidate: true,
    wiki_export_session_limit: 50,
    wiki_export_topic_limit: 100,
    extractor_backend: 'hybrid',
    retrieval_backend: 'fts',
    embedding_candidate_limit: 16,
    llm_model: 'claude-sonnet-4-20250514',
    llm_base_url: '',
    llm_timeout_seconds: 45,
    llm_max_input_chars: 4000,
    embedding_model: 'nomic-embed-text',
    embedding_base_url: 'http://localhost:11434',
    embedding_timeout_seconds: 20,
  },
  fullConfig: {
    plugins: {
      'consolidating-local-memory': {},
    },
  },
  configPath: 'DEMO MODE -- no config file',
};

/* ── Router: returns mock data for a given query type ── */
function mockQuery(queryType, queryArgs) {
  switch (queryType) {
    case 'stats':          return MOCK_STATS;
    case 'facts':          return MOCK_FACTS;
    case 'topics':         return MOCK_TOPICS;
    case 'sessions':       return MOCK_SESSIONS;
    case 'preferences':    return MOCK_PREFERENCES;
    case 'policies':       return MOCK_POLICIES;
    case 'contradictions': return MOCK_CONTRADICTIONS;
    case 'graph':          return MOCK_GRAPH;
    case 'wiki_list':      return MOCK_WIKI_LIST;
    case 'wiki_read': {
      const file = queryArgs?.file || 'index.md';
      const content = MOCK_WIKI_PAGES[file];
      if (content) return { content };
      return { error: `File not found: ${file}` };
    }
    default:
      return { error: `Unknown query type: ${queryType}` };
  }
}

module.exports = { mockQuery, MOCK_CONFIG };
