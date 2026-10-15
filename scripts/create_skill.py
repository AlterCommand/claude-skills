#!/usr/bin/env python3
"""
Interactive or CLI helper to scaffold a new skill and immediately index it into the Vector MCP.

Usage:
    python scripts/create_skill.py --domain marketing-performance --name tiktok-ads-audit --desc "Auditoría de campañas de TikTok Ads..."
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TEMPLATE = """---
name: {name}
description: {desc}
metadata:
  domain: {domain}
---

# {title}

{desc}

## Proceso Operativo

1. **Recolección de Datos**: Identificar los parámetros de entrada y fuentes de información.
2. **Diagnóstico y Análisis**: Evaluar métricas y detectar anomalías.
3. **Recomendaciones**: Entregar directivas accionables priorizadas.

## Reglas y Directivas Críticas

- Mantener la ejecución estructurada.
- Usar scripts deterministas en `scripts/` si aplica.
"""

def create_skill(domain: str, name: str, desc: str):
    # Sanitize
    name = name.strip().lower().replace(" ", "-")
    domain_dir = REPO_ROOT / domain
    if domain == "marketing-performance":
        skill_dir = domain_dir / "skills" / name
    else:
        skill_dir = domain_dir / name

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"

    if skill_file.exists():
        print(f"Error: La skill '{name}' ya existe en {skill_dir}")
        sys.exit(1)

    title = name.replace("-", " ").title()
    content = TEMPLATE.format(name=name, desc=desc, domain=domain, title=title)
    skill_file.write_text(content, encoding="utf-8")
    print(f"[OK] Skill creada exitosamente en: {skill_file.relative_to(REPO_ROOT)}")

    # Create optional scripts dir
    (skill_dir / "scripts").mkdir(exist_ok=True)

    # Trigger indexing
    print("\n[INFO] Ejecutando indexador incremental...")
    import subprocess
    indexer = REPO_ROOT / "scripts" / "skills_indexer.py"
    subprocess.run([sys.executable, str(indexer)])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scaffold and index a new skill")
    parser.add_argument("--domain", "-d", required=True, help="Dominio (ej: engineering-team, marketing-performance, finance, c-level-advisor)")
    parser.add_argument("--name", "-n", required=True, help="Nombre de la skill (ej: tiktok-ads-audit)")
    parser.add_argument("--desc", help="Descripción concisa de la skill y sus disparadores")
    args = parser.parse_args()

    desc = args.desc or f"Especialista y procedimientos para {args.name} en el dominio de {args.domain}."
    create_skill(args.domain, args.name, desc)
