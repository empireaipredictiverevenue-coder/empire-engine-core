"""
EMPIRE V49 · GRAPHIFY BRIDGE
=============================
FastAPI bridge for the Graphify knowledge graph (by safishamsi/graphify).

Loads the extracted graph.json (29K+ nodes, 37K+ edges) and exposes:
  - /api/v1/graphify/stats       — Node/edge/community counts, top nodes
  - /api/v1/graphify/explain     — Plain-language explanation of a node
  - /api/v1/graphify/path        — Shortest path between two nodes
  - /api/v1/graphify/query       — BFS traversal for a question
  - /api/v1/graphify/tree        — Serve the D3 collapsible tree HTML

Also wraps the graphify CLI for dynamic queries (update after code changes).
"""

import os
import json
import re
import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional
from pathlib import Path

log = logging.getLogger("empire.graphify")

GRAPH_DIR = Path("/root/empire-v49/graphify-out")
GRAPH_PATH = GRAPH_DIR / "graph.json"


class GraphifyBridge:
    """In-memory Graphify knowledge graph loader + CLI wrapper."""

    def __init__(self, graph_path: str = str(GRAPH_PATH)):
        self.graph_path = Path(graph_path)
        self.graph: dict = {}
        self.loaded_at: str = ""
        self._degree_cache: dict[str, int] = {}
        self._load_graph()

    def _load_graph(self):
        """Load graph.json into memory and cache degree map."""
        try:
            if not self.graph_path.exists():
                log.warning(f"[graphify] graph.json not found at {self.graph_path}")
                self._degree_cache = {}
                return
            with open(self.graph_path, "r") as f:
                self.graph = json.load(f)
            self.loaded_at = datetime.now(timezone.utc).isoformat()
            # Cache degree map once at load time (static graph)
            self._degree_cache: dict[str, int] = {}
            links = self.graph.get("links", [])
            if isinstance(links, list):
                for link in links:
                    if isinstance(link, dict):
                        s = link.get("source", "")
                        t = link.get("target", "")
                        self._degree_cache[s] = self._degree_cache.get(s, 0) + 1
                        self._degree_cache[t] = self._degree_cache.get(t, 0) + 1
            log.info(f"[graphify] loaded {self.node_count:,} nodes · "
                     f"{self.link_count:,} links · graph size {self.graph_path.stat().st_size / 1e6:.1f}MB")
        except Exception as e:
            log.error(f"[graphify] graph load failed: {e}")
            self.graph = {}
            self._degree_cache = {}

    @property
    def node_count(self) -> int:
        nodes = self.graph.get("nodes", [])
        return len(nodes) if isinstance(nodes, list) else 0

    @property
    def link_count(self) -> int:
        links = self.graph.get("links", [])
        return len(links) if isinstance(links, list) else 0

    @property
    def community_count(self) -> int:
        # Communities are embedded in node data
        nodes = self.graph.get("nodes", [])
        if isinstance(nodes, list):
            communities = set()
            for n in nodes:
                if isinstance(n, dict) and "community" in n:
                    communities.add(n["community"])
            return len(communities)
        return 0

    def stats(self) -> dict:
        """Return graph statistics."""
        nodes = self.graph.get("nodes", [])
        links = self.graph.get("links", [])
        if not isinstance(nodes, list):
            return {"loaded": False, "error": "Graph not loaded"}

        # Use cached degree map (computed at load time)
        top_degree = sorted(
            self._degree_cache.items(), key=lambda x: -x[1]
        )[:20] if hasattr(self, "_degree_cache") else []

        # File type breakdown
        file_types: dict[str, int] = {}
        for node in nodes:
            if isinstance(node, dict):
                ft = node.get("file_type", "unknown")
                file_types[ft] = file_types.get(ft, 0) + 1

        return {
            "loaded": True,
            "loaded_at": self.loaded_at,
            "graph_file": str(self.graph_path),
            "graph_size_mb": round(self.graph_path.stat().st_size / 1e6, 2) if self.graph_path.exists() else 0,
            "nodes": self.node_count,
            "links": self.link_count,
            "communities": self.community_count,
            "top_links_by_degree": [
                {"node": name, "degree": d} for name, d in top_degree[:15]
            ],
            "file_types": file_types,
            "built_at_commit": self.graph.get("built_at_commit", "unknown"),
        }

    def find_node(self, name_or_label: str) -> list[dict]:
        """Search for nodes matching a name or label."""
        nodes = self.graph.get("nodes", [])
        if not isinstance(nodes, list):
            return []
        if self.node_count == 0:
            log.warning("[graphify] find_node called but graph not loaded")
            return []
        query = name_or_label.lower()
        matches = []
        for n in nodes:
            if not isinstance(n, dict):
                continue
            label = (n.get("label") or "").lower()
            nid = (n.get("id") or "").lower()
            source_file = (n.get("source_file") or "").lower()
            if query in label or query in nid or query in source_file:
                matches.append(n)
        return matches[:20]

    def get_neighbors(self, node_id: str) -> dict:
        """Get a node and its immediate (depth=1) neighbors."""
        nodes = self.graph.get("nodes", [])
        links = self.graph.get("links", [])
        if not isinstance(nodes, list) or not isinstance(links, list):
            return {"ok": False, "error": "Graph not loaded — run python3 -m graphify extract"}
        if self.node_count == 0:
            return {"ok": False, "error": "Graph not loaded — run python3 -m graphify extract"}

        # Find the node
        target_node = None
        for n in nodes:
            if isinstance(n, dict) and n.get("id") == node_id:
                target_node = n
                break
        if not target_node:
            return {"node": None, "neighbors": [], "incoming": [], "outgoing": [],
                    "error": f"Node '{node_id}' not found"}

        # Find connections
        incoming = []
        outgoing = []
        for link in links:
            if not isinstance(link, dict):
                continue
            if link.get("target") == node_id:
                incoming.append({
                    "source": link.get("source"),
                    "relation": link.get("relation", "connected_to"),
                    "weight": link.get("weight", 1),
                })
            if link.get("source") == node_id:
                outgoing.append({
                    "target": link.get("target"),
                    "relation": link.get("relation", "connected_to"),
                    "weight": link.get("weight", 1),
                })

        return {
            "ok": True,
            "node": target_node,
            "neighbors": list({l["source"] for l in incoming} | {l["target"] for l in outgoing}),
            "incoming": sorted(incoming, key=lambda x: -x["weight"]),
            "outgoing": sorted(outgoing, key=lambda x: -x["weight"]),
            "degree": len(incoming) + len(outgoing),
        }

    # ── CLI Wrappers ────────────────────────────────────────────────
    async def _run_graphify(self, *args, timeout: int = 30) -> dict:
        """Run the graphify CLI and return parsed output."""
        cmd = ["python3", "-m", "graphify"] + list(args)
        cwd = "/root/empire-v49"
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                return {"ok": False, "error": stderr_str or f"exit {proc.returncode}"}
            return {"ok": True, "output": stdout_str}
        except asyncio.TimeoutError:
            return {"ok": False, "error": f"timeout after {timeout}s"}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    async def explain(self, node_id: str) -> dict:
        """Explain a node via graphify CLI."""
        return await self._run_graphify("explain", node_id, timeout=30)

    async def find_path(self, source: str, target: str) -> dict:
        """Find shortest path between two nodes."""
        return await self._run_graphify("path", source, target, timeout=30)

    async def query(self, question: str) -> dict:
        """BFS traversal query of the graph."""
        return await self._run_graphify("query", question, timeout=30)

    async def update(self) -> dict:
        """Re-extract code files and update the graph."""
        result = await self._run_graphify("update", ".", timeout=120)
        if result.get("ok"):
            self._load_graph()  # Reload after update
        return result

    @property
    def tree_html_path(self) -> str:
        """Path to the generated D3 tree HTML."""
        path = GRAPH_DIR / "GRAPH_TREE.html"
        return str(path) if path.exists() else ""


# ── FastAPI Routes ──────────────────────────────────────────────────

class GraphifyRoutes:
    """Wire Graphify endpoints into FastAPI."""

    def __init__(self, bridge: GraphifyBridge, *,
                 require_auth: Optional[Callable] = None):
        self.bridge = bridge
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Depends, HTTPException, Request
        from fastapi.responses import JSONResponse, HTMLResponse

        @app.get("/api/v1/graphify/stats")
        async def graphify_stats(
            auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Graph statistics: nodes, edges, communities, top degrees, file types."""
            return JSONResponse(self.bridge.stats())

        @app.get("/api/v1/graphify/explain/{node_id}")
        async def graphify_explain(
            node_id: str,
            auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Explain a node — its neighbors, connections, and role in the codebase."""
            # Try in-memory lookup first, fall back to CLI
            neighbors = self.bridge.get_neighbors(node_id)
            if neighbors.get("node"):
                return JSONResponse({
                    "ok": True,
                    "source": "memory",
                    **neighbors,
                })
            # Fall back to graphify CLI
            result = await self.bridge.explain(node_id)
            return JSONResponse(result)

        @app.get("/api/v1/graphify/path/{source}/{target}")
        async def graphify_path(
            source: str, target: str,
            auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Find the shortest path between two nodes in the codebase."""
            result = await self.bridge.find_path(source, target)
            return JSONResponse(result)

        @app.get("/api/v1/graphify/neighbors/{node_id}")
        async def graphify_neighbors(
            node_id: str,
            auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Get a node's neighbors and connections."""
            result = self.bridge.get_neighbors(node_id)
            status = 200 if result.get("ok") else 404
            return JSONResponse(result, status_code=status)

        @app.get("/api/v1/graphify/search")
        async def graphify_search(
            q: str = "",
            auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Search for nodes matching a query."""
            if not q:
                return JSONResponse({"ok": False, "error": "q param required"}, status_code=400)
            matches = self.bridge.find_node(q)
            return JSONResponse({
                "ok": True,
                "query": q,
                "count": len(matches),
                "matches": matches[:20],
            })

        @app.post("/api/v1/graphify/query")
        async def graphify_query(request: Request,
            auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """BFS traversal query of the knowledge graph.
            Body: {question: string}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            question = (body.get("question") or "").strip()
            if not question:
                raise HTTPException(400, "question is required")
            result = await self.bridge.query(question)
            return JSONResponse(result)

        @app.post("/api/v1/graphify/update")
        async def graphify_update(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Re-extract code and update the knowledge graph."""
            result = await self.bridge.update()
            return JSONResponse(result)

        @app.get("/graphify/tree", response_class=HTMLResponse)
        async def graphify_tree_page():
            """Serve the D3 collapsible tree visualization (public)."""
            path = self.bridge.tree_html_path
            if not path:
                raise HTTPException(404, "GRAPH_TREE.html not found. Run: python3 -m graphify tree")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                raise HTTPException(500, f"Failed to read tree HTML: {e}")

        log.info("[graphify] Routes registered · /api/v1/graphify/* + /graphify/tree")
