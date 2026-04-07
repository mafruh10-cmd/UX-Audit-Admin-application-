# UX Audit Generation Flowchart

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         USER UPLOADS SCREENSHOT                              │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 1: UPLOAD & CONTEXT GATHERING                                          │
│  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────────┐     │
│  │ Save Screenshot │  │ Fetch Website    │  │ Store in Session        │     │
│  │ to Storage      │  │ Context (if URL) │  │ (Memory + Local Disk)   │     │
│  └─────────────────┘  └──────────────────┘  └─────────────────────────┘     │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 2: VISION ANALYSIS (Gemini 2.5 Pro)                                    │
│                                                                               │
│  Input:                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  Screenshot (base64) + Website Context (optional) + VISION_PROMPT       ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                  │                                            │
│                                  ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                    GOOGLE GEMINI 2.5 PRO                                 ││
│  │                    (Vision Model)                                        ││
│  │  • Analyzes every UI element                                            ││
│  │  • Identifies layout, typography, colors                                │
│  │  • Lists all buttons, inputs, navigation                                ││
│  │  • Notes accessibility issues                                           ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                  │                                            │
│                                  ▼                                            │
│  Output: Visual Description (6000+ chars)                                    │
│  Example: "The screen shows a dashboard with left sidebar navigation..."     │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 3: KNOWLEDGE BASE INJECTION                                            │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  SYSTEM PROMPT (AUDIT_PROMPT) + KNOWLEDGE_BASE                          ││
│  │                                                                          ││
│  │  "You are a senior UX auditor trained on Saasfactor curriculum..."      ││
│  │                                                                          ││
│  │  + Training Sources:                                                    ││
│  │    • Don't Make Me Think (Steve Krug)                                   ││
│  │    • Refactoring UI (Adam Wathan)                                       ││
│  │    • Designing User Interfaces (Malewicz)                               ││
│  │    • WCAG 2.2 Accessibility Guidelines                                  ││
│  │    • Psychology of Design (106 Cognitive Biases)                        ││
│  │    • Universal Principles of Design (200 principles)                    ││
│  │    • + 8 more training files                                            ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 4: UX AUDIT REASONING (Claude Opus 4.6)                                │
│                                                                               │
│  Input:                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  Visual Description (from Gemini)                                       ││
│  │  + Website Context                                                      ││
│  │  + Knowledge Base (113,000+ chars of UX principles)                     ││
│  │  + AUDIT_PROMPT with rules                                              ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                  │                                            │
│                                  ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                  ANTHROPIC CLAUDE OPUS 4.6                               ││
│  │                  (Reasoning Model with Extended Thinking)                ││
│  │                                                                          ││
│  │  Thinking Budget: 5000 tokens                                            ││
│  │  Max Output: 6000 tokens                                                 │
│  │                                                                          ││
│  │  Process:                                                                ││
│  │  1. Analyze visual description against UX principles                   ││
│  │  2. Identify 7-10 UX issues                                              ││
│  │  3. Cite specific training sources for each finding                    ││
│  │  4. Include WCAG 2.2 violations where applicable                       ││
│  │  5. Generate severity scores (High/Medium/Low)                         ││
│  │  6. Calculate overall_score (0-10) and accessibility_score             │
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                  │                                            │
│                                  ▼                                            │
│  Output: JSON Audit Report                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  {                                                                      ││
│  │    "product_name": "Salesforce",                                        ││
│  │    "screen_name": "Contact Detail View",                                ││
│  │    "overall_score": 6.2,                                                ││
│  │    "accessibility_score": 5.5,                                          ││
│  │    "issues": [                                                          ││
│  │      {                                                                  ││
│  │        "id": "01",                                                      ││
│  │        "title": "Low contrast text",                                    ││
│  │        "severity": "High",                                              ││
│  │        "problem": "Text fails WCAG 2.2 contrast ratio...",              ││
│  │        "reference": "WCAG 2.2 — 1.4.3 Contrast Minimum",               ││
│  │        "annotation": {"x": 45, "y": 20, "w": 30, "h": 10}             ││
│  │      },                                                                 ││
│  │      ... (7-10 issues total)                                           ││
│  │    ]                                                                    ││
│  │  }                                                                      ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 5: POST-PROCESSING                                                     │
│  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────────┐     │
│  │ Annotate Image  │  │ Generate Report  │  │ Save All Artifacts      │     │
│  │ (Numbered       │  │ HTML + Claude    │  │ • Local Disk (primary)  │     │
│  │  markers on     │  │ Prompt +         │  │ • Supabase Storage      │     │
│  │  screenshot)    │  │ Dribbble Data    │  │   (fallback)            │     │
│  └─────────────────┘  └──────────────────┘  └─────────────────────────┘     │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AUDIT COMPLETE ✅                                    │
│                                                                               │
│  User Sees:                                                                   │
│  • Issues at a Glance (numbered cards)                                       │
│  • Overall Score & Accessibility Score                                       │
│  • Detailed findings with UX principles cited                               │
│  • Downloadable HTML Report                                                  │
│  • Claude Redesign Prompt                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Detailed Data Flow

### Knowledge Base Composition (113,375 characters)

```
TRAINING_DATA/
├── training_dmmt.md          → "Don't Make Me Think" principles
├── training_refui.md         → "Refactoring UI" patterns
├── training_dui.md           → "Designing User Interfaces" components
├── training_upd.md           → "Universal Principles of Design" (200 principles)
├── training_psych.md         → "Psych 101" psychological principles
├── training_psydesign.md     → "Psychology of Design" (106 cognitive biases)
├── training_pui.md           → "Practical UI" techniques
├── training_doet.md          → "Design of Everyday Things" (Norman)
├── training_wcag22.md        → WCAG 2.2 Accessibility Guidelines
└── ux_rules_batch1-5.md      → Component-specific UX rules

TOTAL: ~28,000 tokens of UX knowledge
```

### Prompt Structure Sent to Claude Opus

```
[SYSTEM PROMPT - AUDIT_PROMPT]
"You are a senior UX and accessibility auditor trained on..."

[KNOWLEDGE BASE - 113,375 chars]
=== SOURCE: Don't Make Me Think ===
- Billboard Design 101
- Users scan, not read
...

=== SOURCE: Refactoring UI ===
- Use color to support hierarchy
...

[WEBSITE CONTEXT - Optional]
Product: Salesforce
URL: https://salesforce.com
Context: "Salesforce is a CRM platform..."

[VISUAL DESCRIPTION - From Gemini]
"The screen shows a dashboard with:
- Left sidebar navigation with 8 menu items
- Top header with search bar, notifications bell
- Main content area with data table
- 3 action buttons in top right corner
..."

[AUDIT_PROMPT RULES]
- Return valid JSON
- 7-10 findings
- Order by severity (High first)
- Cite exact sources
- Include WCAG criteria for accessibility issues
- Provide annotation coordinates
```

### Response Processing

```
Claude Opus Response (12,000+ chars)
           │
           ▼
    ┌──────────────┐
    │ Parse JSON   │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Validate     │
    │ Structure    │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Annotate     │◄── Uses PIL to draw
    │ Screenshot   │    numbered markers
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Generate     │◄── HTML report with
    │ HTML Report  │    CSS + JS animations
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Save Files   │◄── Local disk first
    │              │    Supabase fallback
    └──────────────┘
```

---

## Key Integration Points

### 1. OpenRouter (API Gateway)
```
Your App ──► OpenRouter ──► Gemini 2.5 Pro (Google)
     │
     └──► OpenRouter ──► Claude Opus 4.6 (Anthropic)
```

### 2. Supabase (Data Layer)
```
┌─────────────┐     ┌─────────────┐
│  PostgreSQL │────►│  Auth/Users │
│  (audits)   │     │  (JWT)      │
└─────────────┘     └─────────────┘
       │
       ▼
┌─────────────┐
│  Storage    │
│  (files)    │
└─────────────┘
```

### 3. Local Fallback (Reliability)
```
Primary:   Supabase Storage
           │
           ├─► 403 Error? ──► Local Disk
           │
           ├─► Timeout? ────► Local Disk
           │
           └─► Network Err? ─► Local Disk
```

---

## Performance Metrics

| Step | Model | Time | Tokens |
|------|-------|------|--------|
| Vision Analysis | Gemini 2.5 Pro | ~15s | 3,000 output |
| UX Reasoning | Claude Opus 4.6 | ~90s | 6,000 output |
| **Total** | - | **~2-3 min** | **~12,000 total** |

---

## Why This Architecture?

1. **Split Pipeline**: Gemini is cheaper/faster for vision, Opus is better for reasoning
2. **Knowledge Base**: Grounds findings in established UX principles, not hallucinations
3. **Local Fallback**: Ensures app works even if Supabase has issues
4. **Streaming UI**: User sees progress steps while waiting for AI
