#!/bin/bash
# Empire AI Autonomous Loop
cd /root/empire-v49
# 1. Update Strategy
python3 mesh_orchestrator.py --run-strategy
# 2. Audit Performance
python3 auditor.py --audit-all
# 3. Save to Master PDF
python3 generate_pdf.py --update
