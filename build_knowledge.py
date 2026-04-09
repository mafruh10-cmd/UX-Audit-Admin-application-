#!/usr/bin/env python3
"""
Build script to pre-compile UX Audit knowledge base.

This script processes all training files and generates a pre-compiled
knowledge_base.json that the app can load instantly at startup.

Run this script whenever training files are modified:
    python build_knowledge.py

The generated knowledge_base.json should be committed to the repository
for production deployments.
"""

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.absolute()
TRAINING_DIR = BASE_DIR / "training_data"
OUTPUT_FILE = BASE_DIR / "knowledge_base.json"

_PRINCIPLE_PATTERNS = (
    "## ", "### ",
    "**Core idea:**", "**UX implication:**", "**Why it matters:**",
    "**Principle:**", "**Example:**", "**Guideline:**",
    "**Rule:**", "**Pattern:**", "**Anti-pattern:**",
    "- ", "1. ", "2. ", "3. ", "4. ", "5. ", "6. ", "7. ", "8. ", "9. ",
    "**", "*", "Severity:", "Reference:", "Note:",
)

_TRAINING_FILES = {
    "training_dmmt.md":       "Don't Make Me Think — Steve Krug",
    "training_dui.md":        "Designing User Interfaces — Dmytro Malewicz",
    "training_psych.md":      "Psych 101 — Paul Kleinman",
    "training_psydesign.md":  "Psychology of Design: 106 Cognitive Biases",
    "training_pui.md":        "Practical UI",
    "training_refui.md":      "Refactoring UI — Adam Wathan & Steve Schoger",
    "training_uitips.md":     "UI Design Tips",
    "training_100things.md":  "100 More Things Every Designer Needs to Know About People",
    "ux_rules_batch1.md":     "UX Component Rules (Part 1)",
    "ux_rules_batch3.md":     "UX Component Rules (Part 3)",
    "ux_rules_batch4.md":     "UX Component Rules (Part 4)",
    "ux_rules_batch5.md":     "UX Component Rules (Part 5)",
    "training_wcag22.md":     "WCAG 2.2 — Web Content Accessibility Guidelines",
    "training_upd.md":        "Universal Principles of Design — Lidwell, Holden & Butler (200 Principles)",
    "training_doet.md":       "The Design of Everyday Things — Don Norman (Revised Edition)",
    "training_saasfactor_ai.md": "Saasfactor AI — Learned Patterns from 2,229 SaaS Screens",
}


def _extract_principles(path: Path, max_chars: int = 8000) -> str:
    """Extract principles from a markdown file."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except FileNotFoundError:
        print(f"  ⚠️  File not found: {path}")
        return ""
    
    out = [l.strip() for l in lines
           if l.strip() and any(p in l for p in _PRINCIPLE_PATTERNS)]
    return "\n".join(out)[:max_chars]


def build_knowledge_base() -> dict:
    """
    Build the complete knowledge base from all training files.
    
    Returns a dict with:
        - content: The concatenated knowledge base string
        - sources: List of source names included
        - stats: Character and token counts
        - version: Build identifier
    """
    parts = []
    sources = []
    failed_sources = []
    
    print("📚 Building UX Audit Knowledge Base...")
    print(f"   Training directory: {TRAINING_DIR}")
    print()
    
    for fname, label in _TRAINING_FILES.items():
        path = TRAINING_DIR / fname
        content = _extract_principles(path)
        
        if content:
            parts.append(f"\n\n=== SOURCE: {label} ===\n{content}")
            sources.append(label)
            char_count = len(content)
            print(f"  ✅ {fname}: {char_count:,} chars")
        else:
            failed_sources.append(fname)
            print(f"  ❌ {fname}: No content extracted")
    
    kb_content = "".join(parts)
    
    result = {
        "content": kb_content,
        "sources": sources,
        "failed_sources": failed_sources,
        "stats": {
            "total_chars": len(kb_content),
            "approx_tokens": len(kb_content) // 4,
            "num_sources": len(sources),
            "total_raw_files": len(_TRAINING_FILES),
        },
        "version": "1.0",
        "build_info": {
            "builder": "build_knowledge.py",
            "training_files": list(_TRAINING_FILES.values()),
        }
    }
    
    return result


def save_knowledge_base(kb_data: dict) -> None:
    """Save the knowledge base to JSON file."""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(kb_data, f, indent=2, ensure_ascii=False)
    
    print()
    print("=" * 50)
    print("✅ Knowledge base built successfully!")
    print(f"   Output: {OUTPUT_FILE}")
    print()
    print("📊 Statistics:")
    print(f"   • Total sources: {kb_data['stats']['num_sources']}")
    print(f"   • Total characters: {kb_data['stats']['total_chars']:,}")
    print(f"   • Approx tokens: {kb_data['stats']['approx_tokens']:,}")
    print(f"   • File size: {OUTPUT_FILE.stat().st_size:,} bytes")
    print()
    
    if kb_data['failed_sources']:
        print("⚠️  Warning: Some files failed to load:")
        for fname in kb_data['failed_sources']:
            print(f"      - {fname}")
        print()
    
    print("💡 Next steps:")
    print("   1. Commit knowledge_base.json to git")
    print("   2. Deploy to Railway")
    print("   3. App will load instantly at startup!")
    print()


def validate_knowledge_base() -> bool:
    """Check if existing knowledge base is up to date."""
    if not OUTPUT_FILE.exists():
        print("⚠️  No existing knowledge_base.json found")
        return False
    
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
        
        # Check if all expected sources are present
        existing_sources = set(existing.get("sources", []))
        expected_sources = set(_TRAINING_FILES.values())
        
        missing = expected_sources - existing_sources
        if missing:
            print(f"⚠️  Knowledge base missing sources: {missing}")
            return False
        
        print(f"✅ Existing knowledge base is valid ({existing['stats']['total_chars']:,} chars)")
        return True
        
    except (json.JSONDecodeError, KeyError) as e:
        print(f"⚠️  Invalid knowledge_base.json: {e}")
        return False


if __name__ == "__main__":
    import sys
    
    # Check for --check flag (validation only)
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        is_valid = validate_knowledge_base()
        sys.exit(0 if is_valid else 1)
    
    # Check for --force flag (rebuild even if valid)
    force_rebuild = len(sys.argv) > 1 and sys.argv[1] == "--force"
    
    if not force_rebuild and OUTPUT_FILE.exists():
        print("🔍 Checking existing knowledge base...")
        if validate_knowledge_base():
            print("\n💡 Use --force to rebuild anyway")
            sys.exit(0)
        print()
    
    # Build and save
    kb_data = build_knowledge_base()
    save_knowledge_base(kb_data)
