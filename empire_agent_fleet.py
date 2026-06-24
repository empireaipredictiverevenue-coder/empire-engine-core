"""
EMPIRE V49 · AGENT FLEET — Role-Based Agent Management
========================================================
Formal role definitions for every agent in the fleet. Each agent has a
defined role with capabilities, parent hierarchy, and task types.

ROLE HIERARCHY
──────────────
traffic_director           — Oversees all traffic channels, allocates budget
├── ppc_specialist         — Pay-per-call + search ads
├── seo_specialist         — Organic content, backlinks
├── native_ads_specialist  — Ad network campaigns + inventory
├── email_sms_specialist   — Outreach sequences
├── social_specialist      — Social ads + community
└── affiliate_specialist   — Recruit + manage partners

lead_gen_director          — Orchestrates the lead gen pipeline
├── lead_scanner           — Finds leads from radar_targets
├── lead_enricher          — Scores + enriches leads
├── contact_scout          — Discovers missing contact info
├── lead_scorer            — Classifies hot/warm/cold
└── lead_converter         — Runs outreach

mesh_controller            — Coordinates task-queue agents
├── mesh_scout             — Finds targets in storm zones
├── mesh_outreach          — Sends messages
├── mesh_dispatcher        — Dispatches contractors
├── mesh_studio_copy       — Writes ad copy
├── mesh_studio_render     — Renders videos
└── quality_analyst        — Scores calls, audits quality

cron_controller            — Coordinates cron agents
├── seo_agent              — Generates content, monitors SEO
├── affiliate_recruiter    — Recruits affiliates
├── predictive_revenue     — Forecasts revenue
├── b2b_lead_scraper       — Scrapes B2B leads
└── fee_watcher            — Monitors settlements

growth_ops_director        — Non-core ops: hacking, intel, media, recon
├── ai_hacking_agent       — Marketing hacks, content arbitrage, social hijacking
├── competitor_intel        — Competitor tracking & intelligence briefs
├── media_lab               — Video rendering, design generation, content creation
└── reconnaissance          — Web scraping, trend monitoring, opportunity scanning
"""

import os
import json
import time
import uuid
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, List, Optional, Any

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from supabase import create_client

log = logging.getLogger("empire.agent_fleet")


# ═════════════════════════════════════════════════════════════════════
# 1. ROLE DEFINITIONS — Canonical role registry
# ═════════════════════════════════════════════════════════════════════

# Every role in the fleet, organized hierarchically.
# Each entry defines: capabilities, task_types, expected heartbeat, and source module.
ROLE_DEFINITIONS: Dict[str, Dict] = {
    # ── Traffic Director & Channel Specialists ──────────────────────
    "traffic_director": {
        "display_name": "Traffic Director",
        "description": "Oversees all traffic channels, allocates budget across channels, sets strategy",
        "parent_role": None,
        "priority": 1,
        "capabilities": [
            "allocate_budget", "set_traffic_strategy", "monitor_all_channels",
            "generate_traffic_report", "optimize_channel_mix",
        ],
        "task_types": ["traffic.allocate", "traffic.report", "traffic.optimize"],
        "source_module": "bots/traffic_specialist.py",
        "expected_interval_minutes": 30,
        "is_core": True,
    },
    "ppc_specialist": {
        "display_name": "PPC Specialist",
        "description": "Manages pay-per-call campaigns and search ad spend",
        "parent_role": "traffic_director",
        "priority": 2,
        "capabilities": [
            "manage_ppc", "optimize_cpl", "monitor_keywords",
            "adjust_bids", "track_conversions",
        ],
        "task_types": ["ppc.optimize", "ppc.report", "ppc.adjust_budget"],
        "source_module": "bots/traffic_specialist.py",
        "expected_interval_minutes": 60,
        "is_core": False,
    },
    "seo_specialist": {
        "display_name": "SEO Specialist",
        "description": "Organic content strategy, backlink monitoring, keyword rank tracking",
        "parent_role": "traffic_director",
        "priority": 3,
        "capabilities": [
            "manage_seo", "track_rankings", "analyze_backlinks",
            "optimize_content", "audit_onpage",
        ],
        "task_types": ["seo.audit", "seo.optimize", "seo.report", "seo.content"],
        "source_module": "bots/seo_agent.py",
        "expected_interval_minutes": 360,
        "is_core": False,
    },
    "native_ads_specialist": {
        "display_name": "Native Ads Specialist",
        "description": "Manages ad network campaigns, creatives, slots, and inventory",
        "parent_role": "traffic_director",
        "priority": 4,
        "capabilities": [
            "manage_native_ads", "optimize_creatives", "manage_inventory",
            "track_ctr", "adjust_budget", "recruit_publishers",
        ],
        "task_types": ["native.optimize", "native.report", "native.create_campaign"],
        "source_module": "bots/traffic_specialist.py",
        "expected_interval_minutes": 30,
        "is_core": False,
    },
    "email_sms_specialist": {
        "display_name": "Email/SMS Specialist",
        "description": "Manages email and SMS outreach sequences, deliverability, compliance",
        "parent_role": "traffic_director",
        "priority": 5,
        "capabilities": [
            "manage_email", "manage_sms", "monitor_deliverability",
            "optimize_sequences", "track_reply_rates",
        ],
        "task_types": ["email.optimize", "sms.optimize", "compliance.check"],
        "source_module": "bots/traffic_specialist.py",
        "expected_interval_minutes": 60,
        "is_core": False,
    },
    "social_specialist": {
        "display_name": "Social Specialist",
        "description": "Social media ads, community engagement, content distribution",
        "parent_role": "traffic_director",
        "priority": 6,
        "capabilities": [
            "manage_social_ads", "engage_community", "distribute_content",
            "track_engagement", "manage_influencers",
        ],
        "task_types": ["social.optimize", "social.engage", "social.report"],
        "source_module": "bots/traffic_specialist.py",
        "expected_interval_minutes": 120,
        "is_core": False,
    },
    "affiliate_specialist": {
        "display_name": "Affiliate Specialist",
        "description": "Recruits affiliates, manages partner relationships, tracks performance",
        "parent_role": "traffic_director",
        "priority": 7,
        "capabilities": [
            "manage_affiliates", "recruit_partners", "track_affiliate_performance",
            "manage_payouts", "optimize_commission",
        ],
        "task_types": ["affiliate.recruit", "affiliate.report", "affiliate.optimize"],
        "source_module": "bots/affiliate_recruiter.py",
        "expected_interval_minutes": 60,
        "is_core": False,
    },
    # ── Lead Gen Director & Pipeline ────────────────────────────────
    "lead_gen_director": {
        "display_name": "Lead Gen Director",
        "description": "Orchestrates the end-to-end lead generation pipeline",
        "parent_role": None,
        "priority": 8,
        "capabilities": [
            "orchestrate_pipeline", "monitor_conversion", "optimize_funnel",
            "generate_forecast", "allocate_lead_budget",
        ],
        "task_types": ["pipeline.run", "pipeline.status", "pipeline.optimize"],
        "source_module": "empire_enrichment_engine.py",
        "expected_interval_minutes": 60,
        "is_core": True,
    },
    "lead_scanner": {
        "display_name": "Lead Scanner",
        "description": "Scans radar_targets and copies qualifying leads to enriched_leads",
        "parent_role": "lead_gen_director",
        "priority": 9,
        "capabilities": ["scan_radar_targets", "dedup_leads", "extract_location"],
        "task_types": ["pipeline.scan", "pipeline.dedup"],
        "source_module": "agents/lead_scanner/scanner.py",
        "expected_interval_minutes": 15,
        "is_core": True,
    },
    "lead_enricher": {
        "display_name": "Lead Enricher",
        "description": "Scores leads using Bayesian probability and feature engineering",
        "parent_role": "lead_gen_director",
        "priority": 10,
        "capabilities": ["score_leads", "engineer_features", "calibrate_probability"],
        "task_types": ["pipeline.enrich", "pipeline.score"],
        "source_module": "agents/lead_enricher/enricher.py",
        "expected_interval_minutes": 15,
        "is_core": True,
    },
    "contact_scout": {
        "display_name": "Contact Scout",
        "description": "Discovers missing phone/email for leads using web sources",
        "parent_role": "lead_gen_director",
        "priority": 11,
        "capabilities": ["discover_contact", "google_places_search", "website_scrape"],
        "task_types": ["pipeline.discover_contact"],
        "source_module": "agents/contact_discovery/discovery.py",
        "expected_interval_minutes": 30,
        "is_core": False,
    },
    "lead_scorer_agent": {
        "display_name": "Lead Scorer",
        "description": "Classifies leads as hot/warm/cold for dispatch priority",
        "parent_role": "lead_gen_director",
        "priority": 12,
        "capabilities": ["classify_leads", "set_priority", "temperature_score"],
        "task_types": ["pipeline.score", "pipeline.classify"],
        "source_module": "agents/lead_scorer/scorer.py",
        "expected_interval_minutes": 30,
        "is_core": True,
    },
    "lead_converter": {
        "display_name": "Lead Converter",
        "description": "Runs outreach sequences (SMS/voice) on top-scored leads",
        "parent_role": "lead_gen_director",
        "priority": 13,
        "capabilities": ["run_outreach", "check_compliance", "qualify_replies"],
        "task_types": ["pipeline.convert", "pipeline.outreach"],
        "source_module": "agents/lead_converter/converter.py",
        "expected_interval_minutes": 30,
        "is_core": True,
    },
    # ── Mesh Controller & Task Agents ───────────────────────────────
    "mesh_controller": {
        "display_name": "Mesh Controller",
        "description": "Coordinates the task-queue agent mesh, assigns tasks, monitors health",
        "parent_role": None,
        "priority": 14,
        "capabilities": [
            "assign_tasks", "monitor_mesh", "restart_agents",
            "balance_load", "track_backlog",
        ],
        "task_types": ["mesh.control", "mesh.health"],
        "source_module": "agent_mesh.py",
        "expected_interval_minutes": 5,
        "is_core": True,
    },
    "mesh_scout": {
        "display_name": "Mesh Scout",
        "description": "Finds targets in storm zones via satellite + weather data",
        "parent_role": "mesh_controller",
        "priority": 15,
        "capabilities": ["find_targets", "storm_scan", "geo_analyze"],
        "task_types": ["scout.find_roofs", "scout.storm_scan"],
        "source_module": "bots/mesh_scout.py",
        "expected_interval_minutes": 60,
        "is_core": True,
    },
    "mesh_outreach": {
        "display_name": "Mesh Outreach",
        "description": "Sends SMS/email sequences to storm-affected property owners",
        "parent_role": "mesh_controller",
        "priority": 16,
        "capabilities": ["send_messages", "run_sequences", "track_responses"],
        "task_types": ["outreach.send", "outreach.sequence"],
        "source_module": "bots/mesh_outreach.py",
        "expected_interval_minutes": 5,
        "is_core": True,
    },
    "mesh_dispatcher": {
        "display_name": "Mesh Dispatcher",
        "description": "Dispatches contractors when leads reply positively",
        "parent_role": "mesh_controller",
        "priority": 17,
        "capabilities": ["dispatch_contractors", "match_leads", "notify_contractors"],
        "task_types": ["dispatch.send", "dispatch.match"],
        "source_module": "bots/mesh_dispatcher.py",
        "expected_interval_minutes": 5,
        "is_core": True,
    },
    "mesh_studio_copy": {
        "display_name": "Copy Writer",
        "description": "Writes ad copy, SMS templates, email drafts for campaigns",
        "parent_role": "mesh_controller",
        "priority": 18,
        "capabilities": ["write_copy", "write_scripts", "a_b_test_copy"],
        "task_types": ["studio.write_copy", "studio.script"],
        "source_module": "bots/mesh_studio_copy.py",
        "expected_interval_minutes": 30,
        "is_core": False,
    },
    "mesh_studio_render": {
        "display_name": "Render Pro",
        "description": "Renders video ads from scripts using FFmpeg + TTS",
        "parent_role": "mesh_controller",
        "priority": 19,
        "capabilities": ["render_videos", "generate_media", "add_audio"],
        "task_types": ["studio.render_reel"],
        "source_module": "bots/mesh_studio_render.py",
        "expected_interval_minutes": 5,
        "is_core": False,
    },
    "quality_analyst": {
        "display_name": "Quality Analyst",
        "description": "Scores call quality, audits compliance, detects anomalies",
        "parent_role": "mesh_controller",
        "priority": 20,
        "capabilities": ["score_calls", "audit_compliance", "detect_anomalies"],
        "task_types": ["revenue.score_call"],
        "source_module": "bots/quality_analyst.py",
        "expected_interval_minutes": 30,
        "is_core": False,
    },
    # ── Cron Controller ─────────────────────────────────────────────
    "cron_controller": {
        "display_name": "Cron Controller",
        "description": "Coordinates all cron-driven background agents",
        "parent_role": None,
        "priority": 21,
        "capabilities": [
            "schedule_crons", "monitor_cron_health", "alert_on_stalls",
        ],
        "task_types": ["cron.schedule", "cron.health"],
        "source_module": "empire_agent_fleet.py",
        "expected_interval_minutes": 60,
        "is_core": True,
    },
    "predictive_revenue": {
        "display_name": "Revenue Forecaster",
        "description": "Predictive revenue modeling, anomaly detection, revenue forecasting",
        "parent_role": "cron_controller",
        "priority": 22,
        "capabilities": ["forecast_revenue", "detect_anomalies", "model_pipeline"],
        "task_types": ["revenue.forecast", "revenue.anomaly"],
        "source_module": "bots/predictive_revenue.py",
        "expected_interval_minutes": 120,
        "is_core": True,
    },
    "predictive_traffic_specialist": {
        "display_name": "Predictive Traffic Specialist",
        "description": "Scores traffic opportunities with a 4-weight model (volume, quality, cost, conversion) via synthetic brain reasoning",
        "parent_role": "traffic_director",
        "priority": 8,
        "capabilities": [
            "score_traffic_opportunities", "predict_channel_performance",
            "generate_recommendations", "weighted_scoring",
            "synthetic_brain_reasoning", "rank_opportunities",
        ],
        "task_types": ["predictive.opportunities", "predictive.score", "predictive.recommend"],
        "source_module": "bots/predictive_traffic_specialist_agent.py",
        "expected_interval_minutes": 60,
        "is_core": False,
    },
    "b2b_lead_scraper": {
        "display_name": "B2B Lead Scraper",
        "description": "Scrapes B2B leads from web directories",
        "parent_role": "cron_controller",
        "priority": 23,
        "capabilities": ["scrape_b2b_leads", "classify_business", "extract_contacts"],
        "task_types": ["b2b.scrape", "b2b.classify"],
        "source_module": "bots/b2b_lead_scraper.py",
        "expected_interval_minutes": 120,
        "is_core": False,
    },
    "fee_watcher": {
        "display_name": "Fee Watcher",
        "description": "Monitors claim settlements and triggers fee events",
        "parent_role": "cron_controller",
        "priority": 24,
        "capabilities": ["monitor_settlements", "trigger_fees", "track_payments"],
        "task_types": ["fee.check", "fee.trigger"],
        "source_module": "agents/fee_watcher/fee_watcher.py",
        "expected_interval_minutes": 60,
        "is_core": True,
    },
    "win_back_ab_test": {
        "display_name": "Win-Back A/B Tester",
        "description": "Runs A/B tests for churn prevention and win-back campaigns",
        "parent_role": "cron_controller",
        "priority": 25,
        "capabilities": ["run_ab_tests", "track_winback", "optimize_retention"],
        "task_types": ["winback.test", "winback.analyze"],
        "source_module": "products/trial_conversion.py",
        "expected_interval_minutes": 360,
        "is_core": False,
    },
    # ── Executive Agent (High-Ticket Sales) ────────────────────
    "executive_agent": {
        "display_name": "Executive Agent",
        "description": "Enterprise high-ticket sales — whale lead scoring, multi-touch executive outreach cadences, complex deal structuring, multi-product bundling, enterprise pipeline tracking",
        "parent_role": "lead_gen_director",
        "priority": 21,
        "capabilities": [
            "score_enterprise_leads", "execute_executive_cadence",
            "structure_complex_deals", "bundle_products",
            "track_enterprise_pipeline", "generate_enterprise_quote",
        ],
        "task_types": [
            "enterprise.score", "enterprise.outreach",
            "enterprise.quote", "enterprise.deal_track",
        ],
        "source_module": "empire_executive_agent.py",
        "expected_interval_minutes": 120,
        "is_core": True,
    },
    # ── Growth Ops Directorate — non-core ops: hacking, intel, media, recon ─
    "growth_ops_director": {
        "display_name": "Growth Ops Director",
        "description": "Orchestrates non-core operations: growth hacking, competitor intelligence, media production (video/design/content), and reconnaissance. Provides unified command center for tactical advantage across all channels.",
        "parent_role": None,
        "priority": 4,
        "capabilities": [
            "orchestrate_ops", "coordinate_agents",
            "unified_dashboard", "cross_op_intelligence",
        ],
        "task_types": [
            "ops.overview", "ops.snapshot",
        ],
        "source_module": "empire_growth_ops.py",
        "expected_interval_minutes": 15,
        "is_core": True,
    },

    # ── AI Hacking Agent (Marketing & Lead Gen) ─────────────────
    "ai_hacking_agent": {
        "display_name": "AI Hacking Agent",
        "description": "Aggressive marketing automation — content arbitrage, social conversation hijacking, ad creative variant generation, cross-channel arbitrage detection, trend jacking, unconventional growth tactics, viral engineering, and audience exploitation patterns",
        "parent_role": "growth_ops_director",
        "priority": 2,
        "capabilities": [
            "content_arbitrage", "social_hijacking",
            "ad_creative_automation", "cross_channel_arbitrage",
            "lead_gen_hacking", "trend_detection",
            "content_syndication", "viral_engineering",
            "audience_exploitation", "channel_flooding",
        ],
        "task_types": [
            "hack.opportunities", "hack.generate_content",
            "hack.syndicate", "hack.trend_scan",
            "hack.viral_engineer", "hack.audience_exploit",
        ],
        "source_module": "empire_ai_hacking_agent.py",
        "expected_interval_minutes": 60,
        "is_core": True,
    },

    # ── Competitor Intel — under growth_ops_director ────────────
    "competitor_intel": {
        "display_name": "Competitor Intel",
        "description": "Autonomous competitor intelligence — tracks competitors across multiple sources, generates intel briefs with LLM enhancement, builds competitive landscape maps, and alerts on competitor moves (pricing, features, expansion, partnerships).",
        "parent_role": "growth_ops_director",
        "priority": 3,
        "capabilities": [
            "track_competitors", "scan_intel",
            "generate_briefs", "map_landscape",
            "detect_moves", "competitive_analysis",
            "llm_enhanced_research", "threat_assessment",
        ],
        "task_types": [
            "intel.track", "intel.scan",
            "intel.brief", "intel.landscape",
        ],
        "source_module": "empire_competitor_intel.py",
        "expected_interval_minutes": 120,
        "is_core": False,
    },

    # ── Media Lab — under growth_ops_director ─────────────────
    "media_lab": {
        "display_name": "Media Lab",
        "description": "Autonomous media production hub — video rendering via mesh_studio_render, design asset generation with LLM creative direction, content creation via content_agent. Unifies all media production under one command center.",
        "parent_role": "growth_ops_director",
        "priority": 4,
        "capabilities": [
            "render_videos", "generate_designs",
            "generate_content", "create_scripts",
            "llm_creative_direction", "content_automation",
        ],
        "task_types": [
            "media.render_video", "media.generate_design",
            "media.create_content", "media.job_status",
        ],
        "source_module": "empire_media_lab.py",
        "expected_interval_minutes": 30,
        "is_core": False,
    },

    # ── Reconnaissance — under growth_ops_director ─────────────
    "reconnaissance": {
        "display_name": "Reconnaissance",
        "description": "Autonomous data gathering and reconnaissance — web scraping, topic research with LLM, trend monitoring and direction detection, opportunity scanning with scoring and prioritization. Feeds intelligence to other ops agents.",
        "parent_role": "growth_ops_director",
        "priority": 5,
        "capabilities": [
            "scan_targets", "research_topics",
            "detect_trends", "find_opportunities",
            "web_scrape", "llm_analysis",
        ],
        "task_types": [
            "recon.scan", "recon.research",
            "recon.trends", "recon.opportunities",
        ],
        "source_module": "empire_reconnaissance.py",
        "expected_interval_minutes": 60,
        "is_core": False,
    },
    # ── Business Growth Agent ──────────────────────────────────
    "business_growth_agent": {
        "display_name": "Business Growth Agent",
        "description": "Autonomous growth analyst — pipeline funnel analysis, market expansion scoring, bottleneck detection, and automated growth actions (prospector sweeps, campaign creation, outreach enrollment)",
        "parent_role": "lead_gen_director",
        "priority": 12,
        "capabilities": [
            "analyze_growth_funnel", "detect_bottlenecks",
            "score_expansion_opportunities", "track_growth_metrics",
            "trigger_prospector_sweep", "generate_campaign",
            "enroll_outreach", "growth_forecasting",
        ],
        "task_types": [
            "growth.analyze", "growth.opportunities",
            "growth.expansion_score", "growth.auto_sweep",
            "growth.auto_campaign", "growth.auto_enroll",
        ],
        "source_module": "empire_business_growth_agent.py",
        "expected_interval_minutes": 120,
        "is_core": True,
    },
    # ── White Label Manager — reseller tiers, container provisioning ─
    "white_label_manager": {
        "display_name": "White-Label Manager",
        "description": "Manages white-label reseller/partner ecosystem — 4 reseller tiers (Starter, Growth, Enterprise, Agency) with per-partner Docker container provisioning, custom branding (logo, colors, custom domain), revenue split configuration, tier-based feature limits, and partner lifecycle management (register, provision, suspend).",
        "parent_role": "sales_director",
        "priority": 34,
        "capabilities": [
            "manage_reseller_tiers", "provision_containers",
            "manage_branding", "track_partner_revenue",
            "handle_partner_lifecycle", "configure_revenue_splits",
            "monitor_container_health", "generate_partner_reports",
        ],
        "task_types": [
            "wl.register", "wl.provision", "wl.brand",
            "wl.suspend", "wl.report", "wl.upgrade_tier",
        ],
        "source_module": "empire_white_label.py",
        "expected_interval_minutes": 30,
        "is_core": True,
    },

    # ── HexStrike AI — internal security agent ─────────────────────
    "hexstrike_security": {
        "display_name": "HexStrike Security",
        "description": "Internal security agent that scans containers, probes API endpoints, detects secrets leaks, and audits pipeline integrity. Runs periodic security scans on Empire's own infrastructure and generates findings with severity scoring. Auto-generates alerts for critical and high-severity issues.",
        "parent_role": "quality_analyst",
        "priority": 45,
        "capabilities": [
            "scan_containers", "probe_api_security",
            "detect_secrets_leaks", "audit_pipeline_integrity",
            "run_full_security_scan", "manage_findings",
            "generate_security_alerts", "monitor_targets",
        ],
        "task_types": [
            "hexstrike.container_scan", "hexstrike.api_scan",
            "hexstrike.secrets_scan", "hexstrike.pipeline_check",
            "hexstrike.full_scan", "hexstrike.manage_findings",
        ],
        "source_module": "empire_hexstrike_ai.py",
        "expected_interval_minutes": 360,
        "is_core": False,
    },

    # ── Closing Agent — full close cycle under sales_director ──────
    "closing_agent": {
        "display_name": "Closing Agent",
        "description": "Takes qualified leads through the full close cycle — voice pipeline management, objection handling, deal structuring and pricing, payment collection (invoices, Solana USDC, Stripe), and onboarding handoff with welcome messaging and kickoff scheduling.",
        "parent_role": "sales_director",
        "priority": 33,
        "capabilities": [
            "manage_close_pipeline", "handle_objections",
            "structure_deals", "collect_payments",
            "generate_invoices", "initiate_onboarding",
            "track_deal_stages", "negotiation_management",
            "pipeline_forecasting", "handoff_to_account_mgmt",
        ],
        "task_types": [
            "close.intake", "close.propose", "close.negotiate",
            "close.payment", "close.onboard", "close.report",
        ],
        "source_module": "empire_closing_agent.py",
        "expected_interval_minutes": 15,
        "is_core": True,
    },

    # ── Compliance Monitor — TCPA/DNC/CCPA enforcement ────────────
    "compliance_monitor": {
        "display_name": "Compliance Monitor",
        "description": "Autonomous compliance enforcement — real-time TCPA/DNC/CCPA checks on all outbound channels (SMS, voice, email), consent lifecycle tracking, violation detection with severity scoring, and compliance audit trail.",
        "parent_role": "sales_director",
        "priority": 32,
        "capabilities": [
            "check_compliance_multi_channel", "detect_violations",
            "track_consent_lifecycle", "enforce_tcpa",
            "enforce_dnc", "enforce_ccpa",
            "generate_compliance_alerts", "audit_compliance",
            "check_quiet_hours", "check_rate_limits",
            "register_opt_out", "run_rules_engine",
        ],
        "task_types": [
            "compliance.check", "compliance.alert",
            "compliance.opt_out", "compliance.audit",
            "compliance.consent", "compliance.ccpa",
        ],
        "source_module": "empire_compliance_monitor.py",
        "expected_interval_minutes": 15,
        "is_core": True,
    },
    # ── Space Reasoner — deep reasoning via Gemini/Claude/Ollama ──────
    "space_reasoner": {
        "display_name": "Space Reasoner",
        "description": "Deep reasoning agent — multi-provider LLM (Gemini free tier → Claude API → Ollama) for complex decisions, strategy evaluation, and structured thinking. Hermes controller consults this for GodMode decisions.",
        "parent_role": None,
        "priority": 1,
        "capabilities": [
            "deep_reasoning", "multi_provider_llm",
            "gemini_api", "claude_api",
            "structured_thinking", "goal_decomposition",
            "decision_analysis", "strategy_evaluation",
        ],
        "task_types": ["space.think", "space.analyze", "space.decide"],
        "source_module": "bots/space_reasoner.py",
        "expected_interval_minutes": 30,
        "is_core": False,
    },

    # ── Sales Director & SDR (New Directorate) ─────────────────────
    "sales_director": {
        "display_name": "Sales Director",
        "description": "Orchestrates the sales pipeline — manages SDRs, closing agents, deal desk, and account management. Owns outbound prospecting, meeting booking, and handoff workflows.",
        "parent_role": None,
        "priority": 30,
        "capabilities": [
            "orchestrate_sales_pipeline", "manage_sdr_team",
            "assign_leads", "track_sales_metrics",
            "optimize_conversion", "forecast_sales",
        ],
        "task_types": ["sales.orchestrate", "sales.forecast", "sales.report"],
        "source_module": "empire_sdr_agent.py",
        "expected_interval_minutes": 60,
        "is_core": True,
    },
    "sdr_agent": {
        "display_name": "SDR Agent",
        "description": "Sales Development Representative — scores inbound leads for ICP fit, runs multi-touch outbound sequences (email → SMS → voice → follow-up), and books qualified meetings for the closing agent.",
        "parent_role": "sales_director",
        "priority": 31,
        "capabilities": [
            "score_icp_fit", "run_outbound_sequences",
            "book_meetings", "qualify_leads",
            "enrich_lead_data", "handoff_to_closing",
            "multi_channel_outreach", "sequence_automation",
        ],
        "task_types": [
            "sdr.score", "sdr.sequence", "sdr.book_meeting",
            "sdr.handoff", "sdr.qualify",
        ],
        "source_module": "empire_sdr_agent.py",
        "expected_interval_minutes": 15,
        "is_core": True,
    },
    # ── AGI & Infrastructure (cron-driven) ───────────────────────
    "agi_revenue": {
        "display_name": "AGI Revenue",
        "description": "AGI-driven revenue optimization and calibration tuning",
        "parent_role": "cron_controller",
        "priority": 26,
        "capabilities": ["agi", "revenue", "optimizer", "tuning"],
        "task_types": ["revenue.agi_tune", "revenue.calibrate"],
        "source_module": "bots/agi_revenue.py",
        "expected_interval_minutes": 120,
        "is_core": True,
    },
    "contractor_sniper": {
        "display_name": "Contractor Sniper",
        "description": "Background worker — recruits contractors via targeted outreach",
        "parent_role": "cron_controller",
        "priority": 27,
        "capabilities": ["recruit_contractors", "target_outreach", "track_signups"],
        "task_types": ["contractor.recruit", "contractor.track"],
        "source_module": "bots/contractor_sniper.py",
        "expected_interval_minutes": 60,
        "is_core": False,
    },
    "hermes_controller": {
        "display_name": "Hermes Controller",
        "description": "Telegram gateway controller — polls Empire1aibot, dispatches commands",
        "parent_role": "cron_controller",
        "priority": 28,
        "capabilities": ["controller", "orchestrator", "telegram_poller"],
        "task_types": ["hermes.poll", "hermes.dispatch"],
        "source_module": "bots/hermes_controller.py",
        "expected_interval_minutes": 5,
        "is_core": True,
    },
    "voice_streaming_agent": {
        "display_name": "Voice Streaming Agent",
        "description": "Vonage voice streaming, TTS, AGI-orchestrated call handling",
        "parent_role": "cron_controller",
        "priority": 29,
        "capabilities": ["voice_streaming", "tts", "vonage"],
        "task_types": ["voice.stream", "voice.synthesize"],
        "source_module": "bots/voice_streaming_agent.py",
        "expected_interval_minutes": 60,
        "is_core": True,
    },
    # ── Storm / Mesh Specialists ───────────────────────────────────
    "storm_predictor": {
        "display_name": "Storm Predictor",
        "description": "Predicts storm paths, scans weather data for lead opportunities",
        "parent_role": "mesh_controller",
        "priority": 21,
        "capabilities": ["storm_scan", "geo_analyze", "find_targets"],
        "task_types": ["scout.storm_scan", "scout.find_roofs"],
        "source_module": "bots/storm_predictor.py",
        "expected_interval_minutes": 60,
        "is_core": True,
    },
    # ── AGI Lane Engine ───────────────────────────────────────────
    "agi_lane_engine": {
        "display_name": "AGI Lane Engine",
        "description": "Orchestrates per-lane strategies, pacing, and AGI routing",
        "parent_role": "lead_gen_director",
        "priority": 14,
        "capabilities": ["orchestrate_lanes", "agi_routing", "set_pacing"],
        "task_types": ["lane.optimize", "lane.pace", "lane.route"],
        "source_module": "bots/agi_lane_engine.py",
        "expected_interval_minutes": 30,
        "is_core": True,
    },
    # ── Swarm Worker ──────────────────────────────────────────────
    "swarm_worker": {
        "display_name": "Swarm Worker",
        "description": "Executes swarm fire tasks — TTS, video rendering, Kokoro speech synthesis",
        "parent_role": "mesh_controller",
        "priority": 31,
        "capabilities": ["swarm", "tts", "kokoro", "ollama", "ffmpeg", "video_render"],
        "task_types": ["swarm.fire", "swarm.strike_video"],
        "source_module": "bots/swarm_worker.py",
        "expected_interval_minutes": 5,
        "is_core": False,
    },
    # ── Idle Asset Detection (Logistics & Transportation) ──────────
    "waste_detector": {
        "display_name": "Idle Asset Detector",
        "description": "Detects idle trailers in logistics compounds via OSM + satellite imagery. Generates leads for brokers, freight companies, and trailer rental.",
        "parent_role": "lead_gen_director",
        "priority": 15,
        "capabilities": [
            "detect_idle_assets", "osm_compound_discovery",
            "waste_scoring", "logistics_intelligence",
            "satellite_hook", "trailer_capacity_estimate",
            "warehouse_waste_detection", "abandoned_building_detection",
        ],
        "task_types": [
            "idle.scan", "idle.score", "idle.report",
            "idle.discover_compounds", "idle.estimate_waste",
        ],
        "source_module": "empire_idle_asset_detector.py",
        "expected_interval_minutes": 360,
        "is_core": False,
    },
    # ── Idle Asset Enrichment (Business Identity Inference) ──────────
    "waste_enricher": {
        "display_name": "Waste Enricher",
        "description": "Enriches logistics compounds with inferred business identity, contact info, and industry classification via OSM metadata + LLM inference",
        "parent_role": "lead_gen_director",
        "priority": 16,
        "capabilities": [
            "enrich_compounds", "infer_identity",
            "classify_industry", "guess_contacts",
        ],
        "task_types": [
            "idle.enrich", "idle.identify_business",
        ],
        "source_module": "empire_idle_asset_detector.py",
        "expected_interval_minutes": 360,
        "is_core": False,
    },
    # ── Idle Asset Outreach (Multi-Model Lead Dispatch) ────────────
    "waste_outreach": {
        "display_name": "Waste Outreach",
        "description": "Enrolls enriched idle asset compounds into email/SMS outreach sequences based on their best business model (lead_gen, consulting, marketplace)",
        "parent_role": "lead_gen_director",
        "priority": 17,
        "capabilities": [
            "enroll_sequences", "dispatch_outreach",
            "multi_model_targeting", "lead_gen_outreach",
            "consulting_outreach", "marketplace_outreach",
        ],
        "task_types": [
            "idle.enroll", "idle.dispatch_email",
            "idle.dispatch_sms", "idle.outreach.report",
        ],
        "source_module": "empire_idle_asset_detector.py",
        "expected_interval_minutes": 360,
        "is_core": False,
    },
    # ── Gas Station Waste Detection (Petroleum Retail) ───────
    "gas_station_detector": {
        "display_name": "Gas Station Waste Detector",
        "description": "Detects waste at gas stations via OSM: idle/abandoned pumps, forecourt disrepair, surrounding site waste. Generates leads for maintenance, audit, and marketplace opportunities.",
        "parent_role": "lead_gen_director",
        "priority": 18,
        "capabilities": [
            "detect_gas_station_waste", "osm_station_discovery",
            "waste_scoring", "forecourt_analysis",
            "abandoned_station_detection", "pump_utilization_estimate",
        ],
        "task_types": [
            "gas.scan", "gas.score", "gas.report",
            "gas.discover_stations", "gas.detect_abandoned",
        ],
        "source_module": "empire_gas_station_waste.py",
        "expected_interval_minutes": 360,
        "is_core": False,
    },
    # ── Gas Station Enrichment (Business Identity Inference) ──
    "gas_station_enricher": {
        "display_name": "Gas Station Enricher",
        "description": "Enriches gas stations with business identity, fuel types, contact info via OSM metadata + LLM inference",
        "parent_role": "lead_gen_director",
        "priority": 19,
        "capabilities": [
            "enrich_stations", "infer_identity",
            "classify_fuel_types", "guess_contacts",
        ],
        "task_types": [
            "gas.enrich", "gas.identify_operator",
        ],
        "source_module": "empire_gas_station_waste.py",
        "expected_interval_minutes": 360,
        "is_core": False,
    },
    # ── Gas Station Outreach (Multi-Model Lead Dispatch) ────
    "gas_station_outreach": {
        "display_name": "Gas Station Outreach",
        "description": "Enrolls scored gas stations into email/SMS outreach based on best business model (lead_gen, consulting, marketplace)",
        "parent_role": "lead_gen_director",
        "priority": 20,
        "capabilities": [
            "enroll_sequences", "dispatch_outreach",
            "multi_model_targeting", "lead_gen_outreach",
            "consulting_outreach", "marketplace_outreach",
        ],
        "task_types": [
            "gas.enroll", "gas.dispatch_email",
            "gas.dispatch_sms", "gas.outreach.report",
        ],
        "source_module": "empire_gas_station_waste.py",
        "expected_interval_minutes": 360,
        "is_core": False,
    },
}


# ═════════════════════════════════════════════════════════════════════
# 2. AGENT FLEET MANAGER
# ═════════════════════════════════════════════════════════════════════

class AgentFleet:
    """
    Manages the entire agent fleet: role definitions, agent registration,
    heartbeat tracking, task routing, and health monitoring.

    This is the central authority for knowing what agents exist, what they do,
    and whether they're running correctly.
    """

    def __init__(self, get_db: Callable):
        self.get_db = get_db
        self.roles = dict(ROLE_DEFINITIONS)  # mutable copy
        self._heartbeats: Dict[str, dict] = {}  # agent_name -> {last_ping, status, ...}
        self._fleet_loop_task: Optional[asyncio.Task] = None

    # ── Role Queries ────────────────────────────────────────────────

    def get_role(self, role_name: str) -> Optional[Dict]:
        """Get a role definition by name."""
        return self.roles.get(role_name)

    def get_children(self, parent_role: str) -> List[Dict]:
        """Get all child roles of a parent."""
        return [r for name, r in self.roles.items()
                if r.get("parent_role") == parent_role]

    def get_roles_by_capability(self, capability: str) -> List[Dict]:
        """Find all roles that have a specific capability."""
        return [r for name, r in self.roles.items()
                if capability in r.get("capabilities", [])]

    def get_roles_by_task_type(self, task_type: str) -> List[tuple]:
        """Find all roles that handle a specific task type."""
        return [(name, r) for name, r in self.roles.items()
                if task_type in r.get("task_types", [])]

    def get_hierarchy(self) -> Dict:
        """Return the full role hierarchy tree."""
        roots = [name for name, r in self.roles.items() if r.get("parent_role") is None]

        tree = []
        for root in sorted(roots, key=lambda n: self.roles[n].get("priority", 99)):
            role = self.roles[root]
            node = {
                "role": root,
                "display_name": role.get("display_name", root),
                "description": role.get("description", ""),
                "children": [],
            }
            children_names = [name for name, r in self.roles.items()
                              if r.get("parent_role") == root]
            children_names.sort(key=lambda n: self.roles[n].get("priority", 99))
            for child_name in children_names:
                child = self.roles[child_name]
                node["children"].append({
                    "role": child_name,
                    "display_name": child.get("display_name", child_name),
                    "description": child.get("description", ""),
                    "capabilities": child.get("capabilities", []),
                })
            tree.append(node)

        return tree

    # ── Heartbeat / Registration ───────────────────────────────────

    async def register_agent(
        self,
        agent_name: str,
        role_name: str,
        status: str = "ACTIVE",
        meta: Optional[Dict] = None,
    ) -> None:
        """Register or update an agent's heartbeat in the database."""
        if role_name not in self.roles:
            log.warning(f"[fleet] unknown role '{role_name}' for agent '{agent_name}'")
            return

        role = self.roles[role_name]
        db = self.get_db()

        try:
            db.table("agent_registry").upsert({
                "agent_name": agent_name,
                "role_name": role_name,
                "status": status,
                "last_ping": datetime.now(timezone.utc).isoformat(),
                "capabilities": role.get("capabilities", []),
                "task_types": role.get("task_types", []),
                "meta": meta or {},
            }, on_conflict="agent_name").execute()
        except Exception as e:
            log.debug(f"[fleet] register_agent error ({agent_name}): {e}")

        # Also update in-memory
        self._heartbeats[agent_name] = {
            "role": role_name,
            "last_ping": time.time(),
            "status": status,
        }

    async def seed_roles_to_db(self) -> None:
        """Seed all role definitions to the agent_roles table."""
        db = self.get_db()
        for role_name, role_def in self.roles.items():
            try:
                db.table("agent_roles").upsert({
                    "role_name": role_name,
                    "display_name": role_def.get("display_name", ""),
                    "description": role_def.get("description", ""),
                    "parent_role": role_def.get("parent_role"),
                    "priority": role_def.get("priority", 5),
                    "capabilities": role_def.get("capabilities", []),
                    "task_types": role_def.get("task_types", []),
                    "source_module": role_def.get("source_module", ""),
                    "expected_interval_minutes": role_def.get("expected_interval_minutes", 30),
                    "auto_restart": role_def.get("auto_restart", True),
                    "is_core": role_def.get("is_core", False),
                    "is_active": True,
                }, on_conflict="role_name").execute()
            except Exception as e:
                log.debug(f"[fleet] seed role {role_name} error: {e}")
        log.info(f"[fleet] seeded {len(self.roles)} roles to database")

    async def purge_stale_agents(self, max_age_hours: int = 24) -> Dict:
        """Delete stale agent registrations from the database.

        Purges two categories:
          1. Orphaned registrations with no role_name (old format)
          2. Agents whose last_ping is older than max_age_hours and
             who are not currently in the in-memory heartbeat list
             (i.e. they're not actively running in this hub instance).

        Returns {ok, purged_orphaned, purged_expired, kept_active}.
        """
        db = self.get_db()
        purged_orphaned = 0
        purged_expired = 0
        kept = 0

        now = datetime.now(timezone.utc)
        cutoff_dt = now - timedelta(hours=max_age_hours)
        cutoff_epoch = cutoff_dt.timestamp()

        try:
            # ── 1. Delete orphaned registrations (role_name is NULL) ──
            res = db.table("agent_registry").select("agent_name").is_("role_name", "null").execute()
            orphaned = [r["agent_name"] for r in (res.data or [])]
            if orphaned:
                db.table("agent_registry").delete().in_("agent_name", orphaned).execute()
                purged_orphaned = len(orphaned)
                log.info(f"[fleet] purged {purged_orphaned} orphaned registrations (no role)")

            # ── 2. Delete expired registrations (last_ping too old) ──
            all_rows = db.table("agent_registry").select(
                "agent_name, last_ping"
            ).order("agent_name").execute()

            expired_names = []
            for row in (all_rows.data or []):
                name = row.get("agent_name", "")
                last_ping = row.get("last_ping", "")

                # Keep agents we have in-memory heartbeats for (actively running)
                if name in self._heartbeats:
                    kept += 1
                    continue

                # Check if last_ping is older than cutoff
                if last_ping:
                    try:
                        ping_epoch = datetime.fromisoformat(
                            last_ping.replace("Z", "+00:00")
                        ).timestamp()
                        if ping_epoch < cutoff_epoch:
                            expired_names.append(name)
                        else:
                            kept += 1
                    except Exception:
                        expired_names.append(name)
                else:
                    # No last_ping at all — definitely stale
                    expired_names.append(name)

            if expired_names:
                db.table("agent_registry").delete().in_("agent_name", expired_names).execute()
                purged_expired = len(expired_names)
                log.info(f"[fleet] purged {purged_expired} expired registrations (>{max_age_hours}h)")

            return {
                "ok": True,
                "purged_orphaned": purged_orphaned,
                "purged_expired": purged_expired,
                "kept_active": kept,
                "cutoff": cutoff_dt.isoformat(),
            }
        except Exception as e:
            log.error(f"[fleet] purge error: {e}")
            return {"ok": False, "error": str(e)[:200]}

    # ── Fleet Monitoring ────────────────────────────────────────────

    async def fleet_status(self) -> Dict:
        """Return the current status of all registered agents."""
        db = self.get_db()
        try:
            rows = db.table("agent_registry").select(
                "agent_name, role_name, status, last_ping, capabilities"
            ).order("agent_name").execute()
        except Exception:
            rows = type("obj", (), {"data": []})()

        active = []
        stale = []
        unknown = []

        now = time.time()
        for row in (rows.data or []):
            agent_name = row.get("agent_name", "")
            role_name = row.get("role_name", "")
            status = row.get("status", "UNKNOWN")
            last_ping = row.get("last_ping", "")

            role = self.roles.get(role_name, {})
            expected_interval = role.get("expected_interval_minutes", 30) * 60

            # Check if stale
            is_stale = False
            if last_ping:
                try:
                    ping_time = datetime.fromisoformat(last_ping.replace("Z", "+00:00")).timestamp()
                    age = now - ping_time
                    is_stale = age > expected_interval * 2
                except Exception:
                    pass

            entry = {
                "agent_name": agent_name,
                "role_name": role_name,
                "display_name": role.get("display_name", role_name),
                "status": status,
                "last_ping": last_ping,
                "is_stale": is_stale,
                "expected_interval_min": role.get("expected_interval_minutes", 30),
            }

            if is_stale or status == "STALE":
                stale.append(entry)
            elif status == "ACTIVE":
                active.append(entry)
            else:
                unknown.append(entry)

        return {
            "total": len(rows.data or []),
            "active": active,
            "stale": stale,
            "unknown": unknown,
            "roles_defined": len(self.roles),
        }

    async    def route_task(
        self,
        task_type: str,
        task_payload: Dict,
        preferred_role: Optional[str] = None,
    ) -> Optional[str]:
        """Route a task to the appropriate role. Returns the role name or None."""
        # If a specific role is preferred, check it
        if preferred_role and preferred_role in self.roles:
            if task_type in self.roles[preferred_role].get("task_types", []):
                return preferred_role

        # Find any role that handles this task type
        matching = self.get_roles_by_task_type(task_type)
        if matching:
            # Return the highest priority (lowest number)
            matching.sort(key=lambda t: t[1].get("priority", 99))
            return matching[0][0]  # role name from (name, role) tuple

        return None

    # ── Fleet Health Loop ───────────────────────────────────────────

    async def start_fleet_loop(self, interval_seconds: int = 60):
        """Background loop: check fleet health, seed roles, detect stalls."""
        log.info(f"[fleet] Fleet health loop starting (interval={interval_seconds}s)")

        # Seed roles on first run
        try:
            await self.seed_roles_to_db()
        except Exception as e:
            log.warning(f"[fleet] seed failed on startup: {e}")

        while True:
            try:
                status = await self.fleet_status()
                stale_count = len(status.get("stale", []))
                if stale_count > 0:
                    stale_names = [s["agent_name"] for s in status["stale"]]
                    log.warning(f"[fleet] {stale_count} stale agent(s): {stale_names}")
            except Exception as e:
                log.debug(f"[fleet] health check error: {e}")

            await asyncio.sleep(interval_seconds)

    # ── Traffic Specialist Upgrade ──────────────────────────────────

    async def traffic_specialist_cycle(
        self,
        specialist_instance: Any,  # TrafficSpecialist instance
    ) -> Dict:
        """
        Run a traffic specialist cycle, reporting results as channel-specific roles.
        This wraps the existing TrafficSpecialist.run_cycle() and maps its channel
        results to the appropriate role.
        """
        if not specialist_instance:
            return {"ok": False, "error": "no specialist instance"}

        # Register as Traffic Director
        await self.register_agent(
            agent_name="traffic_specialist",
            role_name="traffic_director",
            status="ACTIVE",
        )

        # Run the cycle
        from bots.traffic_specialist import get_traffic_specialist
        specialist = get_traffic_specialist()

        cycle_result = await specialist.run_cycle() if hasattr(specialist, 'run_cycle') else {}

        # Map channel results to specialist roles
        channels = {
            "ppc": "ppc_specialist",
            "seo": "seo_specialist",
            "native_ads": "native_ads_specialist",
            "email": "email_sms_specialist",
            "sms": "email_sms_specialist",
            "social": "social_specialist",
            "affiliate": "affiliate_specialist",
        }

        channel_insights = cycle_result.get("channel_insights", {})
        for channel_key, role_name in channels.items():
            if channel_key in channel_insights:
                await self.register_agent(
                    agent_name=f"{role_name}.worker",
                    role_name=role_name,
                    status="ACTIVE",
                    meta={"last_action": str(channel_insights[channel_key])[:200]},
                )

        return {
            "ok": True,
            "director": "traffic_director",
            "channels_reported": list(channels.keys()),
            "actions_taken": cycle_result.get("actions_taken", 0),
        }

    def snapshot(self) -> Dict:
        """Quick snapshot of fleet state."""
        return {
            "roles_defined": len(self.roles),
            "registered_agents": len(self._heartbeats),
            "hierarchy": self.get_hierarchy(),
        }


# ═════════════════════════════════════════════════════════════════════
# 3. FASTAPI ROUTES
# ═════════════════════════════════════════════════════════════════════

def register_fleet_routes(
    app: FastAPI,
    *,
    fleet: AgentFleet,
    require_auth: Optional[Callable] = None,
):
    """Wire agent fleet routes on the hub."""

    # Shared auth fallback — use require_auth if provided, else no auth
    _auth_dep = Depends(require_auth) if require_auth else None

    @app.get("/api/v1/fleet/roles")
    async def list_roles(auth: dict = _auth_dep):
        """Return all defined agent roles with hierarchy."""
        return {
            "roles": fleet.roles,
            "hierarchy": fleet.get_hierarchy(),
            "total": len(fleet.roles),
        }

    @app.get("/api/v1/fleet/roles/{role_name}")
    async def get_role(role_name: str, auth: dict = _auth_dep):
        """Return a single role definition with its children."""
        role = fleet.get_role(role_name)
        if not role:
            raise HTTPException(404, f"Role '{role_name}' not found")
        children = fleet.get_children(role_name)
        return {
            "role": role_name,
            "definition": role,
            "children": children,
            "child_count": len(children),
        }

    @app.get("/api/v1/fleet/status")
    async def fleet_status(auth: dict = _auth_dep):
        """Return current fleet status — all registered agents, health, stalls."""
        return await fleet.fleet_status()

    @app.post("/api/v1/fleet/seed")
    async def seed_roles(auth: dict = _auth_dep):
        """Seed all role definitions to the database. Any authenticated operator may seed."""
        await fleet.seed_roles_to_db()
        return {"ok": True, "roles_seeded": len(fleet.roles)}

    @app.get("/api/v1/fleet/snapshot")
    async def fleet_snapshot(auth: dict = _auth_dep):
        """Quick fleet snapshot for dashboards."""
        return fleet.snapshot()

    @app.post("/api/v1/fleet/route")
    async def route_task(
        request: Request,
        auth: dict = _auth_dep,
    ):
        """Route a task to the appropriate role."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        task_type = (body.get("task_type") or "").strip()
        payload = body.get("payload", {})
        preferred_role = (body.get("preferred_role") or "").strip() or None

        if not task_type:
            raise HTTPException(400, "task_type is required")

        role = await fleet.route_task(task_type, payload, preferred_role)
        if role:
            return {"ok": True, "role": role, "task_type": task_type}
        return {"ok": False, "error": f"No role handles task type '{task_type}'"}

    @app.post("/api/v1/fleet/purge")
    async def purge_stale(
        request: Request,
        auth: dict = _auth_dep,
    ):
        """Purge stale agent registrations — orphaned entries and agents inactive >24h.
        Optional body: {max_age_hours: 48} to override the 24h default."""
        max_age_hours = 24
        try:
            body = await request.json()
        except Exception:
            body = None
        if isinstance(body, dict) and "max_age_hours" in body:
            try:
                max_age_hours = max(1, min(int(body["max_age_hours"]), 720))
            except (ValueError, TypeError):
                pass
        result = await fleet.purge_stale_agents(max_age_hours=max_age_hours)
        return result

    # ── Watcher Findings Routes ────────────────────────────────────

    @app.get("/api/v1/fleet/watcher-findings")
    async def list_watcher_findings(
        limit: int = Query(50, ge=1, le=200),
        unacknowledged_only: bool = Query(False),
        finding_type: Optional[str] = Query(None),
        severity: Optional[str] = Query(None),
        auth: dict = _auth_dep,
    ):
        """Return recent watcher findings with optional filters.

        Query params:
          - limit: max rows (1-200, default 50)
          - unacknowledged_only: bool — only show not-acknowledged
          - finding_type: filter by type (pm2_error|stale_heartbeat|agent_error)
          - severity: filter by severity (critical|warning)
        """
        db = fleet.get_db()
        try:
            query = db.table("watcher_findings").select("*").order("created_at", desc=True).limit(limit)
            if unacknowledged_only:
                query = query.eq("acknowledged", False)
            if finding_type:
                query = query.eq("finding_type", finding_type)
            if severity:
                query = query.eq("severity", severity)
            r = query.execute()
            findings = r.data or []
            return {"findings": findings, "count": len(findings)}
        except Exception as e:
            log.warning(f"[fleet] watcher-findings query failed: {e}")
            return {"findings": [], "count": 0, "error": str(e)[:200]}

    @app.patch("/api/v1/fleet/watcher-findings/{finding_id}/acknowledge")
    async def acknowledge_finding(finding_id: str, auth: dict = _auth_dep):
        """Mark a watcher finding as acknowledged (operator has seen it)."""
        db = fleet.get_db()
        try:
            r = db.table("watcher_findings").update({
                "acknowledged": True,
                "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", finding_id).execute()
            return {"ok": True, "finding_id": finding_id, "updated": len(r.data or [])}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    @app.patch("/api/v1/fleet/watcher-findings/{finding_id}/fix")
    async def fix_finding(finding_id: str, auth: dict = _auth_dep):
        """Mark a watcher finding as fixed (resolved)."""
        db = fleet.get_db()
        try:
            r = db.table("watcher_findings").update({
                "fixed": True,
                "fixed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", finding_id).execute()
            return {"ok": True, "finding_id": finding_id, "updated": len(r.data or [])}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    @app.get("/api/v1/fleet/watcher-stats")
    async def watcher_stats(
        days: int = Query(7, ge=1, le=90),
        auth: dict = _auth_dep,
    ):
        """Return watcher findings stats: severity breakdown, type breakdown,
        acknowledged/fixed rates, and daily error counts.

        Query params:
          - days: lookback window (1-90, default 7)
        """
        db = fleet.get_db()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        stats = {
            "lookback_days": days,
            "total": 0,
            "critical": 0,
            "warning": 0,
            "by_type": {},
            "acknowledged": 0,
            "unacknowledged": 0,
            "fixed": 0,
            "unfixed": 0,
            "daily_counts": [],
        }
        try:
            r = db.table("watcher_findings").select("*").gte("created_at", cutoff).execute()
            rows = r.data or []
            stats["total"] = len(rows)
            for row in rows:
                sev = row.get("severity", "")
                ftype = row.get("finding_type", "unknown")
                acknowledged = row.get("acknowledged", False)
                fixed = row.get("fixed", False)
                created = (row.get("created_at") or "")[:10]

                if sev == "critical":
                    stats["critical"] += 1
                else:
                    stats["warning"] += 1

                stats["by_type"][ftype] = stats["by_type"].get(ftype, 0) + 1

                if acknowledged:
                    stats["acknowledged"] += 1
                else:
                    stats["unacknowledged"] += 1

                if fixed:
                    stats["fixed"] += 1
                else:
                    stats["unfixed"] += 1

                # Daily counts
                day_entry = None
                for d in stats["daily_counts"]:
                    if d["date"] == created:
                        day_entry = d
                        break
                if not day_entry:
                    day_entry = {"date": created, "total": 0, "critical": 0, "warning": 0}
                    stats["daily_counts"].append(day_entry)
                day_entry["total"] += 1
                if sev == "critical":
                    day_entry["critical"] += 1
                else:
                    day_entry["warning"] += 1

            stats["daily_counts"].sort(key=lambda d: d["date"])
        except Exception as e:
            log.warning(f"[fleet] watcher-stats query failed: {e}")
            stats["error"] = str(e)[:200]

        return stats

    log.info("[fleet] Routes registered — /api/v1/fleet/{roles,status,seed,snapshot,route,purge,watcher-findings,watcher-stats}")
