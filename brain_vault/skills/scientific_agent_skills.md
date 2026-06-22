---
type: skill
name: scientific.scientific-agent-skills
version: 1.0.0
description: 140+ scientific domain skills for bioinformatics, genomics, drug discovery, physics, materials science, and clinical research
tags: [domain:science, bioinformatics, genomics, research, databases]
timeout_seconds: 120
max_retries: 2
execution_mode: llm
required_params:
  - domain
dependencies: []
---

# Scientific Agent Skills — 140+ Scientific Domain Skills

Cloned from https://github.com/K-Dense-AI/scientific-agent-skills.
Installed at `/root/scientific-agent-skills/`.

## Overview

A curated collection of agent skills and AI-powered workflows for scientific domains. Includes access to 100+ scientific databases covering bioinformatics, genomics, cheminformatics, drug discovery, physics, materials science, and clinical research.

## Supported Domains

- **Bioinformatics**: Gene analysis, sequence alignment, phylogenetics
- **Genomics**: Variant calling, GWAS, expression analysis
- **Cheminformatics**: Molecular modeling, drug-likeness, QSAR
- **Drug Discovery**: Target identification, lead optimization, docking
- **Physics**: Particle physics, astrophysics, computational physics
- **Materials Science**: Crystal structure, property prediction
- **Clinical Research**: Trial design, data analysis, regulatory compliance

## Parameters

- `domain`: Scientific domain (bioinformatics, genomics, cheminformatics, drug-discovery, physics, materials-science, clinical)
- `task`: Specific research task within the domain
- `query`: Research question or data to analyze
- `databases`: Specific databases to query (optional)

## Installation

Skills can be installed via:
```bash
gh skill install <skill-name>
# or
npx skills add <skill-url>
```

## Usage

Search the scientific-agent-skills repository for skills relevant to the given domain and task. Return the instructions, database access methods, and analysis workflows.
