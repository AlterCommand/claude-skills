#!/usr/bin/env python3
"""
Skills Router MCP Server (stdio).

Provides 3 high-leverage meta-tools for Antigravity:
1. skills_search: Semantic + BM25 hybrid search over the 2,363 skills.
2. skills_load: Dynamic Just-In-Time retrieval of SKILL.md rules/sections.
3. skills_exec: Deterministic execution of python scripts within skills.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = REPO_ROOT / ".cache" / "skills_db"
DB_PATH = DB_DIR / "skills_catalog.db"
EMBEDDINGS_PATH = DB_DIR / "embeddings.npy"
IDS_PATH = DB_DIR / "skill_ids.json"

class SkillsRouter:
    def __init__(self):
        self.db_path = DB_PATH
        self.matrix: Optional[np.ndarray] = None
        self.skill_ids: List[str] = []
        self.embedding_model = None
        self.last_mtime: float = 0.0
        self._load_cache()

    def _load_cache(self):
        """Load in-memory matrix and IDs if available or updated."""
        if EMBEDDINGS_PATH.exists() and IDS_PATH.exists():
            try:
                mtime = EMBEDDINGS_PATH.stat().st_mtime
                if mtime > self.last_mtime:
                    self.matrix = np.load(EMBEDDINGS_PATH)
                    self.skill_ids = json.loads(IDS_PATH.read_text(encoding="utf-8"))
                    self.last_mtime = mtime
                    sys.stderr.write(f"Loaded/Reloaded vector cache: {len(self.skill_ids)} skills\n")
            except Exception as e:
                sys.stderr.write(f"Failed to load vector cache: {e}\n")

        try:
            from fastembed import TextEmbedding
            self.embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")
        except Exception as e:
            sys.stderr.write(f"FastEmbed not available for online queries: {e}\n")

    def search(self, query: str, domain: Optional[str] = None, top_k: int = 3) -> List[Dict[str, Any]]:
        """Hybrid Search: Vector Cosine Similarity + BM25 FTS5 with RRF."""
        self._load_cache()
        top_k = min(max(1, top_k), 10)
        scores: Dict[str, float] = {}

        # 1. Vector Search
        if self.embedding_model and self.matrix is not None and self.skill_ids:
            try:
                q_emb = list(self.embedding_model.embed([query]))[0]
                q_vec = np.array(q_emb, dtype=np.float32)
                q_norm = np.linalg.norm(q_vec)
                if q_norm > 0:
                    q_vec /= q_norm
                    sims = self.matrix @ q_vec
                    top_indices = np.argsort(sims)[::-1][:top_k * 3]
                    for rank, idx in enumerate(top_indices):
                        sid = self.skill_ids[idx]
                        scores[sid] = scores.get(sid, 0.0) + (1.0 / (60.0 + rank + 1.0))
            except Exception as e:
                sys.stderr.write(f"Vector search failed: {e}\n")

        # 2. BM25 Search via SQLite FTS5
        if self.db_path.exists():
            try:
                conn = sqlite3.connect(self.db_path)
                cur = conn.cursor()
                # Clean query for FTS
                fts_query = re.sub(r'[^\w\s-]', '', query).strip()
                if fts_query:
                    words = fts_query.split()
                    fts_term = " OR ".join([f'"{w}"*' for w in words[:6]])
                    cur.execute("""
                        SELECT skill_id, rank
                        FROM skills_fts
                        WHERE skills_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                    """, (fts_term, top_k * 3))
                    for rank, row in enumerate(cur.fetchall()):
                        sid = row[0]
                        scores[sid] = scores.get(sid, 0.0) + (1.0 / (60.0 + rank + 1.0))
                conn.close()
            except Exception as e:
                sys.stderr.write(f"FTS search failed: {e}\n")

        if not scores:
            return []

        # Sort combined results
        sorted_sids = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)

        # Retrieve metadata
        results = []
        if self.db_path.exists():
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            for sid in sorted_sids:
                cur.execute("""
                    SELECT skill_id, name, domain, description, rel_path, has_scripts, scripts_json
                    FROM skills WHERE skill_id = ?
                """, (sid,))
                row = cur.fetchone()
                if not row:
                    continue
                s_id, name, s_domain, desc, rel_path, has_scr, scr_json = row
                if domain and domain.lower() not in s_domain.lower():
                    continue

                scripts = json.loads(scr_json) if scr_json else []
                results.append({
                    "skill_id": s_id,
                    "name": name,
                    "domain": s_domain,
                    "description": desc[:180] + "..." if len(desc) > 180 else desc,
                    "rel_path": rel_path,
                    "has_scripts": bool(has_scr),
                    "scripts": scripts[:3],
                    "relevance_score": round(scores[sid] * 100, 2)
                })
                if len(results) >= top_k:
                    break
            conn.close()

        return results

    def load(self, skill_id: str, section: str = "rules") -> Dict[str, Any]:
        """Load specific sections of a skill's SKILL.md without overflowing context."""
        if not self.db_path.exists():
            return {"error": "Database not initialized. Run build_skills_index first."}

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT name, domain, description, rel_path, scripts_json FROM skills WHERE skill_id = ?", (skill_id,))
        row = cur.fetchone()
        conn.close()

        if not row:
            return {"error": f"Skill '{skill_id}' not found."}

        name, domain, desc, rel_path, scr_json = row
        full_path = REPO_ROOT / rel_path
        if not full_path.exists():
            return {"error": f"Skill file {rel_path} does not exist on disk."}

        content = full_path.read_text(encoding="utf-8", errors="replace")

        # Section formatting
        if section == "summary":
            return {
                "skill_id": skill_id,
                "name": name,
                "domain": domain,
                "description": desc,
                "path": rel_path
            }
        elif section == "scripts":
            scripts = json.loads(scr_json) if scr_json else []
            return {
                "skill_id": skill_id,
                "scripts": scripts,
                "script_dir": str(full_path.parent / "scripts")
            }
        elif section == "rules":
            # Cap at 2500 characters to keep context ultra-lean
            rules_content = content[:2500]
            if len(content) > 2500:
                rules_content += "\n\n...[Truncated: Use section='full' if detailed reference is required]..."
            return {
                "skill_id": skill_id,
                "name": name,
                "domain": domain,
                "instructions": rules_content
            }
        else: # "full"
            return {
                "skill_id": skill_id,
                "name": name,
                "domain": domain,
                "instructions": content
            }

    def execute(self, skill_id: str, script_name: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
        """Execute a deterministic Python script from the skill's scripts directory."""
        if not self.db_path.exists():
            return {"error": "Database not initialized."}

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT rel_path FROM skills WHERE skill_id = ?", (skill_id,))
        row = cur.fetchone()
        conn.close()

        if not row:
            return {"error": f"Skill '{skill_id}' not found."}

        rel_path = row[0]
        skill_dir = (REPO_ROOT / rel_path).parent
        script_path = skill_dir / "scripts" / script_name

        if not script_path.exists():
            return {"error": f"Script '{script_name}' not found in {skill_dir}/scripts"}

        cmd = [sys.executable, str(script_path)] + (args or [])
        try:
            proc = subprocess.run(cmd, cwd=str(skill_dir), capture_output=True, text=True, timeout=60)
            return {
                "skill_id": skill_id,
                "script": script_name,
                "returncode": proc.returncode,
                "stdout": proc.stdout[:3000],
                "stderr": proc.stderr[:1000]
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Script execution timed out after 60 seconds."}
        except Exception as e:
            return {"error": f"Execution error: {str(e)}"}

# MCP stdio JSON-RPC Handler
def run_mcp_server():
    router = SkillsRouter()

    TOOLS = [
        {
            "name": "skills_search",
            "description": "Busca semánticamente dentro del catálogo de 2,363 skills locales la herramienta, procedimiento o guía requerida. Consume <150 tokens.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Objetivo, tarea o tecnología buscada (ej: 'optimizar consultas BigQuery', 'auditoría de Meta Ads', 'análisis financiero de SaaS')"
                    },
                    "domain": {
                        "type": "string",
                        "description": "Filtro opcional por dominio: 'engineering', 'marketing-performance', 'c-level-advisor', 'product-team', 'finance', etc."
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 3,
                        "description": "Cantidad de resultados a retornar (por defecto 3, máximo 5 para evitar sobrecargar contexto)"
                    }
                },
                "required": ["query"]
            }
        },
        {
            "name": "skills_load",
            "description": "Carga bajo demanda las reglas e instrucciones operativas de una skill específica identificada mediante skills_search.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "skill_id": {
                        "type": "string",
                        "description": "El ID exacto de la skill devuelto por skills_search (ej: 'meta-ads-audit', 'bigquery-sql')"
                    },
                    "section": {
                        "type": "string",
                        "enum": ["rules", "summary", "scripts", "full"],
                        "default": "rules",
                        "description": "Nivel de detalle a cargar ('rules' carga las directivas operativas acotadas a 2500 chars; 'summary' metadatos; 'full' documento completo)"
                    }
                },
                "required": ["skill_id"]
            }
        },
        {
            "name": "skills_exec",
            "description": "Ejecuta un script determinista de Python ubicado en la carpeta scripts/ de una skill y retorna el resultado estructurado.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "skill_id": {
                        "type": "string",
                        "description": "ID de la skill dueña del script"
                    },
                    "script_name": {
                        "type": "string",
                        "description": "Nombre del archivo de script (ej: 'seo_checker.py', 'audit_account.py')"
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Argumentos CLI pasados al script"
                    }
                },
                "required": ["skill_id", "script_name"]
            }
        }
    ]

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except Exception:
            continue

        msg_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            res = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "skills-router", "version": "1.0.0"},
                    "capabilities": {"tools": {}}
                }
            }
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            res = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS}
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})
            tool_res = {}

            if tool_name == "skills_search":
                query = args.get("query", "")
                domain = args.get("domain")
                top_k = args.get("top_k", 3)
                results = router.search(query, domain, top_k)
                tool_res = {"content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False, indent=2)}]}
            elif tool_name == "skills_load":
                skill_id = args.get("skill_id", "")
                section = args.get("section", "rules")
                data = router.load(skill_id, section)
                tool_res = {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}]}
            elif tool_name == "skills_exec":
                skill_id = args.get("skill_id", "")
                script_name = args.get("script_name", "")
                cli_args = args.get("args", [])
                out = router.execute(skill_id, script_name, cli_args)
                tool_res = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=2)}]}
            else:
                tool_res = {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}]}

            res = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": tool_res
            }
        elif method == "ping":
            res = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        else:
            res = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}

        sys.stdout.write(json.dumps(res) + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    run_mcp_server()
