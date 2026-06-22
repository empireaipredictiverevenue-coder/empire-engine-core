-- ═══════════════════════════════════════════════════════════════════════════
-- EMPIRE V49 · SOVEREIGN AGI TASK TYPES
-- ═══════════════════════════════════════════════════════════════════════════
-- Documents sovereign.* task types for the agent_task_queue.
-- Idempotent · safe to re-run.
-- ═══════════════════════════════════════════════════════════════════════════

-- Update the task_type column comment to include sovereign AGI types
COMMENT ON COLUMN public.agent_task_queue.task_type IS
  'Task type identifier. Supported namespaces:
   scout.find_roofs | outreach.draft_email | studio.write_script | studio.render_reel
   revenue.connect_buyer | revenue.score_call | swarm.fire | swarm.strike_video
   email.execute | design.execute | marketing.execute
   browser.scrape | browser.automate | scrape.web | scrape.crawl
   agentic.plan | agentic.review | autoresearch.run | autoresearch.orchestrate
   sovereign.strategy_decide | sovereign.self_aware | sovereign.niche_analyze
   sovereign.regime_detect | sovereign.agi_optimize
   memory.store | memory.retrieve | prompts.optimize | scientific.research
   marketing.* (45 skills) | email.* (25 skills) | design.* (24 skills) | social.* | content.*';

-- Ensure mesh_sovereign role exists in agent_roles (FK constraint on agent_registry)
INSERT INTO public.agent_roles (role_name, description)
VALUES (
    'mesh_sovereign',
    'Sovereign AGI Matrix worker — processes sovereign.* tasks (strategy decisions, self-awareness snapshots, Bayesian niche analysis, regime detection, AGI weight optimization)'
)
ON CONFLICT (role_name) DO NOTHING;

-- Ensure mesh.sovereign is registered in agent_registry
INSERT INTO public.agent_registry (agent_name, status, enabled, capabilities, task_types, role_name)
VALUES (
    'mesh.sovereign',
    'ACTIVE',
    true,
    '["sovereign","agi","strategy","self-awareness","bayesian","optimization","regime-detection"]'::jsonb,
    ARRAY[
        'sovereign.strategy_decide',
        'sovereign.self_aware',
        'sovereign.niche_analyze',
        'sovereign.regime_detect',
        'sovereign.agi_optimize'
    ],
    'mesh_sovereign'
)
ON CONFLICT (agent_name)
DO UPDATE SET
    capabilities = EXCLUDED.capabilities,
    task_types = EXCLUDED.task_types,
    role_name = EXCLUDED.role_name,
    last_ping = now();
