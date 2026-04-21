# Saasfactor AI — Component & Layout Patterns

**Generated**: 2026-04-21 14:13
**Dataset**: 3,319 screens across 26 products

---

## Component Density (Per Screen Average)

- **Buttons**: 11.4
- **Input fields**: 9.2
- **Cards**: 0.5
- **Tabs**: 1.8
- **Navigation items**: 0.3
- **Icons**: 131.6
- **Toggles**: 43.7
- **Dropdowns**: 0.0
- **CTAs**: 7.3
- **Text blocks**: 34.7

---

## Severity Benchmarks

### High Severity Flags
- Dashboard with >50 UI elements (information overload)
- Form with >10 inputs on single screen (cognitive overload)
- No primary CTA on transactional screen (conversion blocker)
- Navigation with >10 visible items (Hick's Law violation)
- List with >30 items and no search/filter (findability issue)

### Medium Severity Flags
- Dashboard with 36-50 elements (approaching overload)
- List with 20-30 items and no search (minor findability issue)
- Settings without visual grouping (organization issue)
- Form with 7-10 inputs (approaching cognitive limit)
- Missing breadcrumb on deep navigation (orientation issue)

---

## Layout Pattern Guidelines

- **List**: 89.7% of all screens (2,978 screens)
- **Dashboard**: 10.2% of all screens (339 screens)
- **Mixed**: 0.1% of all screens (2 screens)

---

## Reference Format for Audit Citations

When citing Saasfactor AI in audit findings, use this format:

- "Saasfactor AI — Dashboard Layouts: typical range 25-35 elements"
- "Saasfactor AI — List Screens: 67% include search for >20 items"
- "Saasfactor AI — Component Density: average 6 buttons per screen"
- "Saasfactor AI — Severity Flags: Dashboards >50 elements = High severity"

---

*Patterns are derived from atomic component extraction (YOLOv8 + OpenCV + OCR) across trained SaaS products.*
