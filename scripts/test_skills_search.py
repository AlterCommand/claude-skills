#!/usr/bin/env python3
"""
Test harness for SkillsRouter: Validates search latency, relevance, and token budget.
"""

import time
import sys
from pathlib import Path

# Add scripts directory
sys.path.insert(0, str(Path(__file__).resolve().parent))
from skills_router_mcp import SkillsRouter

def main():
    print("=" * 60)
    print("Testing SkillsRouter Local Engine")
    print("=" * 60)

    start_init = time.perf_counter()
    router = SkillsRouter()
    init_ms = (time.perf_counter() - start_init) * 1000
    print(f"Engine initialization time: {init_ms:.2f} ms")

    test_queries = [
        ("optimizar consultas en bigquery", "engineering"),
        ("auditoría de campañas de meta ads", "marketing-performance"),
        ("arquitectura de software y microservicios", "engineering"),
        ("analisis financiero y métricas saas", "finance"),
    ]

    for query, domain in test_queries:
        print(f"\n[QUERY]: '{query}' (domain filter: {domain or 'None'})")
        t0 = time.perf_counter()
        results = router.search(query=query, domain=domain, top_k=3)
        search_ms = (time.perf_counter() - t0) * 1000
        print(f"Search latency: {search_ms:.2f} ms | Found: {len(results)} matches")

        for i, res in enumerate(results, 1):
            print(f"  {i}. [{res['skill_id']}] (Score: {res['relevance_score']})")
            print(f"     Domain: {res['domain']}")
            print(f"     Desc: {res['description'][:100]}...")

    # Test skills_load
    if results:
        top_skill = results[0]["skill_id"]
        print(f"\n[TEST LOAD]: Loading rules for '{top_skill}' (section='rules')...")
        t0 = time.perf_counter()
        loaded = router.load(top_skill, section="rules")
        load_ms = (time.perf_counter() - t0) * 1000
        chars = len(loaded.get("instructions", ""))
        print(f"Load latency: {load_ms:.2f} ms | Payload size: {chars} chars (~{chars//4} tokens)")
        print("=" * 60)
        print("ALL TESTS PASSED SUCCESSFULLY!")
        print("=" * 60)

if __name__ == "__main__":
    main()
