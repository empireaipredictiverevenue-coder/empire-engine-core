# Task Routing Reference

## Task Type → Agent Mapping
| Task Type | Assigned Agent | SLA | Priority |
|---|---|---|---|
| scout.find_roofs | mesh.scout | 30 min | High |
| outreach.draft_email | mesh.outreach | 5 min | Critical |
| studio.write_script | mesh.studio_copy | 60 min | Medium |
| studio.render_reel | mesh.studio_render | 10 min | High |
| revenue.connect_buyer | mesh.dispatcher | 5 min | Critical |
| revenue.score_call | mesh.quality | 15 min | Medium |
| swarm.fire | mesh.swarm_worker | 5 min | High |
| swarm.strike_video | mesh.swarm_worker | 10 min | Medium |
| marketing.email.campaign | mesh.marketing | 1440 min | Medium |
| marketing.cold.outreach | mesh.marketing | 240 min | High |
| marketing.conversion | mesh.marketing | 120 min | High |
| marketing.sms.campaign | mesh.marketing | 120 min | Critical |
| marketing.seo.content | mesh.marketing | 10080 min | Low |
| marketing.paid.ads | mesh.marketing | 720 min | High |
| marketing.copy | mesh.marketing | 1440 min | High |
| marketing.social.publish | mesh.marketing | 1440 min | Medium |
| content.seo | mesh.marketing | 60 min | Medium |
| marketing.advertising | mesh.marketing | 720 min | High |
| marketing.publishing | mesh.marketing | 1440 min | Medium |
| marketing.seo-expert | mesh.marketing | 120 min | High |
| social.scraper | mesh.marketing | 60 min | Medium |
| design.ui.component | mesh.design | 60 min | Medium |
| design.ui.layout | mesh.design | 120 min | Medium |
| design.ui.screen | mesh.design | 120 min | High |
| design.ux.flow | mesh.design | 60 min | High |
| design.ux.wireframe | mesh.design | 120 min | Medium |
| design.ux.prototype | mesh.design | 240 min | High |
| design.ux.research | mesh.design | 480 min | Medium |
| design.visual.brand | mesh.design | 1440 min | Medium |
| design.visual.color | mesh.design | 120 min | High |
| design.visual.typography | mesh.design | 120 min | Medium |
| design.visual.iconography | mesh.design | 180 min | Low |
| design.visual.data-viz | mesh.design | 240 min | Medium |
| design.system.tokens | mesh.design | 240 min | Low |
| design.system.component-library | mesh.design | 480 min | Medium |
| design.system.documentation | mesh.design | 240 min | Low |
| design.motion.microinteractions | mesh.design | 60 min | Medium |
| design.motion.transition | mesh.design | 120 min | Medium |
| design.motion.loading | mesh.design | 60 min | Low |
| design.a11y.color | mesh.design | 120 min | High |
| design.a11y.interaction | mesh.design | 180 min | Critical |
| design.a11y.audit | mesh.design | 240 min | High |
| design.ops.workflow | mesh.design | 240 min | Medium |
| design.ops.critique | mesh.design | 120 min | Medium |
| design.ops.design-sprint | mesh.design | 480 min | High |
| design.web-builder | mesh.design | 120 min | High |
| email.strategy | mesh.email | 240 min | Medium |
| email.calendar | mesh.email | 120 min | Medium |
| email.sequence | mesh.email | 120 min | High |
| email.drip | mesh.email | 180 min | Medium |
| email.nurture | mesh.email | 240 min | High |
| email.re-engagement | mesh.email | 120 min | High |
| email.deliverability | mesh.email | 60 min | Critical |
| email.authentication | mesh.email | 60 min | High |
| email.warmup | mesh.email | 1440 min | High |
| email.list-hygiene | mesh.email | 240 min | High |
| email.compliance-can-spam | mesh.email | 60 min | Critical |
| email.compliance-gdpr | mesh.email | 120 min | Critical |
| email.compliance-casl | mesh.email | 120 min | High |
| email.copy-subject | mesh.email | 60 min | High |
| email.copy-body | mesh.email | 120 min | High |
| email.copy-cta | mesh.email | 60 min | High |
| email.analytics | mesh.email | 240 min | Low |
| email.ab-testing | mesh.email | 180 min | Medium |
| email.optimization | mesh.email | 240 min | Medium |
| email.api | mesh.email | 120 min | Medium |
| email.template | mesh.email | 240 min | Medium |
| email.personalization | mesh.email | 120 min | Medium |
| email.inbound | mesh.email | 120 min | High |
| email.provider-resend | mesh.email | 60 min | High |
| email.provider-listmonk | mesh.email | 120 min | Medium |
| email.execute | mesh.email | 30 min | High |
| design.execute | mesh.design | 30 min | High |
| browser.scrape | mesh.browser | 30 min | High |
| browser.automate | mesh.browser | 60 min | Medium |
| prompts.optimize | mesh.marketing | 15 min | High |
| memory.store | mesh.scout | 5 min | Medium |
| memory.retrieve | mesh.scout | 5 min | Critical |
| scrape.web | mesh.scraper | 30 min | High |
| scrape.crawl | mesh.scraper | 120 min | Medium |
| scientific.research | mesh.marketing | 60 min | Low |
| agentic.plan | mesh.orchestrator | 30 min | High |
| agentic.review | mesh.orchestrator | 30 min | High |
| autoresearch.run | mesh.autoresearch | 60 min | Medium |
| autoresearch.orchestrate | mesh.orchestrator | 360 min | Low |

## Retry Policy
- Failed tasks: retry up to 3 times with exponential backoff (30s, 2min, 5min)
- Blocked tasks: notify operator via IPC event every 30 min
- Stale In-Progress: reassign after 2× SLA timeout

## Agent Health Rules
- Expected heartbeat: every 30s (configurable)
- Missed 3 heartbeats → mark as STALE → try restart
- Missed 6 heartbeats → mark as ERROR → alert operator
- Auto-recover: restart ERROR agents every 5 min (max 5 attempts)
