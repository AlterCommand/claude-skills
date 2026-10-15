#!/usr/bin/env python3
"""
Skills Indexer for Claude Skills / Antigravity Optimization.

Indexes all SKILL.md files into a local SQLite database with:
1. Lexical BM25 Search (FTS5)
2. Semantic Dense Vector Embeddings (FastEmbed BAAI/bge-small-en-v1.5 + NumPy)
3. Incremental caching (SHA-256 hashing)
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from fastembed import TextEmbedding
    HAS_FASTEMBED = True
except ImportError:
    HAS_FASTEMBED = False

# Default DB location
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = REPO_ROOT / ".cache" / "skills_db"
DB_PATH = DB_DIR / "skills_catalog.db"
EMBEDDINGS_PATH = DB_DIR / "embeddings.npy"
IDS_PATH = DB_DIR / "skill_ids.json"

# Exclusion patterns
EXCLUDE_DIRS = {
    ".git", ".gemini", ".claude", ".codex", ".hermes", ".vibe",
    "tests", "evals", "eval-workspace", "node_modules", "__pycache__", "venv", ".venv"
}

def extract_frontmatter(content: str) -> Tuple[Dict, str]:
    """Extract YAML frontmatter and markdown body."""
    metadata = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body = parts[2].strip()
            for line in fm_text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    metadata[key] = val
    return metadata, body

def get_domain_from_path(rel_path: Path) -> str:
    """Infer domain/category from the top-level or parent folder."""
    parts = rel_path.parts
    if len(parts) > 1:
        return parts[0]
    return "general"

def scan_skills(repo_root: Path) -> List[Dict]:
    """Scan all valid SKILL.md files in repository."""
    skills = []
    seen_ids = set()

    for skill_path in repo_root.rglob("SKILL.md"):
        # Check exclusions
        if any(part in EXCLUDE_DIRS for part in skill_path.parts):
            continue

        rel_path = skill_path.relative_to(repo_root)
        try:
            content = skill_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            continue

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        meta, body = extract_frontmatter(content)

        parent_dir = skill_path.parent
        domain = get_domain_from_path(rel_path)
        
        # Skill ID computation
        name = meta.get("name") or parent_dir.name
        skill_id = name
        if skill_id in seen_ids:
            skill_id = f"{domain}/{name}"
            if skill_id in seen_ids:
                skill_id = f"{rel_path.parent.as_posix()}"
        seen_ids.add(skill_id)

        description = meta.get("description", "")
        if not description:
            # Fallback to first paragraph of body
            paragraphs = [p.strip() for p in body.split("\n\n") if p.strip() and not p.strip().startswith("#")]
            description = paragraphs[0][:250] if paragraphs else f"Skill from {domain}"

        # Extract first 400 chars of body overview
        body_clean = re.sub(r'#+\s*', '', body)
        overview = body_clean[:400].replace("\n", " ").strip()

        # Check for deterministic scripts
        scripts_dir = parent_dir / "scripts"
        available_scripts = []
        if scripts_dir.is_dir():
            for script_file in scripts_dir.glob("*.py"):
                available_scripts.append(script_file.name)

        skills.append({
            "skill_id": skill_id,
            "name": name,
            "domain": domain,
            "description": description,
            "rel_path": rel_path.as_posix(),
            "content_hash": content_hash,
            "overview": overview,
            "has_scripts": 1 if available_scripts else 0,
            "scripts_json": json.dumps(available_scripts),
            "search_text": f"{name} ({domain}): {description}. {overview}"
        })

    return skills

def init_database(db_path: Path):
    """Initialize SQLite tables and FTS5 index."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            skill_id TEXT PRIMARY KEY,
            name TEXT,
            domain TEXT,
            description TEXT,
            rel_path TEXT,
            content_hash TEXT,
            overview TEXT,
            has_scripts INTEGER,
            scripts_json TEXT,
            embedding BLOB
        )
    """)

    # Check if FTS5 table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='skills_fts'")
    if not cur.fetchone():
        cur.execute("""
            CREATE VIRTUAL TABLE skills_fts USING fts5(
                skill_id,
                name,
                domain,
                description,
                overview
            )
        """)

    conn.commit()
    conn.close()

def build_index(verbose: bool = True):
    """Main indexing workflow."""
    start_time = time.time()
    init_database(DB_PATH)

    if verbose:
        print(f"Scanning skills in {REPO_ROOT}...")
    skills = scan_skills(REPO_ROOT)
    if verbose:
        print(f"Found {len(skills)} skills across repository.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Get existing hashes
    cur.execute("SELECT skill_id, content_hash FROM skills")
    existing_hashes = dict(cur.fetchall())

    to_index = []
    for s in skills:
        sid = s["skill_id"]
        if sid not in existing_hashes or existing_hashes[sid] != s["content_hash"]:
            to_index.append(s)

    if verbose:
        print(f"Skills needing indexing/updating: {len(to_index)}")

    embedding_model = None
    if HAS_FASTEMBED and to_index:
        if verbose:
            print("Loading FastEmbed BAAI/bge-small-en-v1.5 model...")
        embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")

    # Generate embeddings and store in DB
    if to_index and embedding_model:
        texts = [s["search_text"] for s in to_index]
        if verbose:
            print(f"Computing embeddings for {len(texts)} skills on CPU...")
        embeddings = list(embedding_model.embed(texts))

        for s, emb in zip(to_index, embeddings):
            emb_bytes = np.array(emb, dtype=np.float32).tobytes()
            # Upsert into skills
            cur.execute("""
                INSERT INTO skills (skill_id, name, domain, description, rel_path, content_hash, overview, has_scripts, scripts_json, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(skill_id) DO UPDATE SET
                    name=excluded.name,
                    domain=excluded.domain,
                    description=excluded.description,
                    rel_path=excluded.rel_path,
                    content_hash=excluded.content_hash,
                    overview=excluded.overview,
                    has_scripts=excluded.has_scripts,
                    scripts_json=excluded.scripts_json,
                    embedding=excluded.embedding
            """, (
                s["skill_id"], s["name"], s["domain"], s["description"], s["rel_path"],
                s["content_hash"], s["overview"], s["has_scripts"], s["scripts_json"], emb_bytes
            ))

            # Upsert FTS5
            cur.execute("DELETE FROM skills_fts WHERE skill_id = ?", (s["skill_id"],))
            cur.execute("""
                INSERT INTO skills_fts (skill_id, name, domain, description, overview)
                VALUES (?, ?, ?, ?, ?)
            """, (s["skill_id"], s["name"], s["domain"], s["description"], s["overview"]))

        conn.commit()
    elif to_index and not HAS_FASTEMBED:
        if verbose:
            print("FastEmbed not available. Indexing in FTS5 only...")
        for s in to_index:
            cur.execute("""
                INSERT INTO skills (skill_id, name, domain, description, rel_path, content_hash, overview, has_scripts, scripts_json, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(skill_id) DO UPDATE SET
                    name=excluded.name,
                    domain=excluded.domain,
                    description=excluded.description,
                    rel_path=excluded.rel_path,
                    content_hash=excluded.content_hash,
                    overview=excluded.overview,
                    has_scripts=excluded.has_scripts,
                    scripts_json=excluded.scripts_json
            """, (
                s["skill_id"], s["name"], s["domain"], s["description"], s["rel_path"],
                s["content_hash"], s["overview"], s["has_scripts"], s["scripts_json"]
            ))
            cur.execute("DELETE FROM skills_fts WHERE skill_id = ?", (s["skill_id"],))
            cur.execute("""
                INSERT INTO skills_fts (skill_id, name, domain, description, overview)
                VALUES (?, ?, ?, ?, ?)
            """, (s["skill_id"], s["name"], s["domain"], s["description"], s["overview"]))
        conn.commit()

    # Export full matrix to .npy and .json for microsecond in-memory matrix multiplication
    cur.execute("SELECT skill_id, embedding FROM skills WHERE embedding IS NOT NULL")
    rows = cur.fetchall()
    if rows:
        ids = [r[0] for r in rows]
        vectors = [np.frombuffer(r[1], dtype=np.float32) for r in rows]
        mat = np.stack(vectors)
        # Normalize for cosine similarity
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        norm_mat = mat / norms

        np.save(EMBEDDINGS_PATH, norm_mat)
        IDS_PATH.write_text(json.dumps(ids), encoding="utf-8")
        if verbose:
            print(f"Exported in-memory matrix: shape {norm_mat.shape} to {EMBEDDINGS_PATH}")

    conn.close()
    elapsed = time.time() - start_time
    if verbose:
        print(f"Index complete in {elapsed:.2f} seconds. DB size: {DB_PATH.stat().st_size / (1024*1024):.2f} MB")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build skills search index")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet output")
    args = parser.parse_args()
    build_index(verbose=not args.quiet)
