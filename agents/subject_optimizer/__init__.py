"""EMPIRE · Cold Email Subject Line Optimizer

Autonomous A/B testing loop for cold email subject lines.
Reads historical open rates, scores the current test, and
generates new mutations via LLM.

Usage:
    python3 -m agents.subject_optimizer.optimizer
    python3 -m agents.subject_optimizer.optimizer --dry-run
"""
