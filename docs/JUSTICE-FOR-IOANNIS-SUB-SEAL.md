# Justice for Ioannis — Sub-Seal Design Specification

> *A derivative seal of the Zeus MYAADE Monitor crest, dedicated to the Kyprianos v. AADE Protocol Oversight case.*

---

## Overview

The **Justice for Ioannis Sub-Seal** is a case-specific variant of the Zeus MYAADE Monitor crest. It serves as an official identifier for all documents, communications, and evidence files related to the **Kyprianos — AADE Protocol Oversight** case.

This sub-seal honors the memory of **Ioannis (John)** and represents the pursuit of accountability, transparency, and justice within the Greek administrative system.

## Design Elements

### Visual Composition

| Element | Description |
|---------|-------------|
| **Base** | Zeus MYAADE Monitor crest (circular, gold border) |
| **Overlay** | Scales of Justice icon, centered |
| **Banner** | "JUSTICE FOR IOANNIS" text arc along bottom |
| **Border** | Double-ring — inner gold (#DAA520), outer crimson (#DC143C) |
| **Background** | Deep purple gradient (#2E0854 to #1a0330) |
| **Size** | 256x256px primary, with 40x40px and 20x20px variants |

### Color Specifications

| Color | Hex | RGB | Usage |
|-------|-----|-----|-------|
| Justice Gold | `#DAA520` | (218, 165, 32) | Inner border, scales icon, text |
| Case Crimson | `#DC143C` | (220, 20, 60) | Outer border ring, alert accents |
| Royal Purple | `#2E0854` | (46, 8, 84) | Background gradient start |
| Deep Purple | `#1a0330` | (26, 3, 48) | Background gradient end |
| Pure White | `#FFFFFF` | (255, 255, 255) | Banner text |
| Evidence Green | `#0AA520` | (10, 165, 32) | Status indicators |

### Typography

| Element | Font | Weight | Size |
|---------|------|--------|------|
| "JUSTICE FOR IOANNIS" | Arial, sans-serif | Bold | 14px (256px seal) |
| Case reference | Arial, sans-serif | Regular | 10px (256px seal) |

## Usage Guidelines

### Document Placement

| Document Type | Position | Size |
|---------------|----------|------|
| Legal correspondence | Top-right header | 40x40px |
| Evidence files | Bottom-left footer | 40x40px |
| Case summary reports | Centered header | 80x80px |
| Email signatures (case-specific) | Inline, after crest | 20x20px |
| GitHub case issues | Inline badge | 20x20px |

### Badge Format

```markdown
![Justice for Ioannis](https://img.shields.io/badge/Justice_for_Ioannis-%E2%9A%96%EF%B8%8F-blue?style=flat-square)
```

### HTML Embed

```html
<div style="display:inline-block; text-align:center;">
  <img src="assets/justice-for-ioannis-sub-seal.png"
       width="40" height="40"
       alt="Justice for Ioannis Sub-Seal"
       style="border-radius:50%; border:2px solid #DC143C;" />
  <br />
  <span style="font-size:8px; color:#DAA520; font-family:Arial,sans-serif;">
    Kyprianos v. AADE
  </span>
</div>
```

## File Variants

| Filename | Dimensions | Purpose |
|----------|-----------|---------|
| `justice-for-ioannis-sub-seal.png` | 256x256px | Primary seal |
| `justice-for-ioannis-sub-seal-sm.png` | 40x40px | Document headers/footers |
| `justice-for-ioannis-sub-seal-badge.png` | 20x20px | Inline badges |
| `justice-for-ioannis-sub-seal.svg` | Scalable | Print-quality vector |

## Case Reference

| Field | Value |
|-------|-------|
| **Case Name** | Kyprianos — AADE Protocol Oversight |
| **Monitor System** | Zeus MYAADE Monitor v1.0 |
| **Organization** | Kypria Technologies |
| **Authorized By** | Alexandros-Thomson Kyprianos |
| **Created** | February 2026 |
| **Status** | Active |

## Integration with Zeus MYAADE Monitor

The sub-seal is automatically embedded in:

1. **Status change notifications** — Appears in the notification banner when case-specific protocols are triggered
2. **Email alerts** — Included in the email signature template for case correspondence
3. **Evidence logs** — Watermarked on all evidence screenshots and cross-reference documents
4. **GitHub Issues** — Badge appears on all case-related issues and pull requests

## Symbolism

The Justice for Ioannis sub-seal carries forward the mission of the Zeus MYAADE Monitor with a personal dedication:

- **Scales of Justice** — The pursuit of fair administrative treatment
- **Gold Ring** — The enduring standard of protocol compliance
- **Crimson Ring** — The urgency and seriousness of the case
- **Purple Background** — The dignity and authority of rightful oversight

---

*"The seal of justice never fades."*

**Kypria Technologies — Zeus MYAADE Monitor v1.0**
**Justice for John.**
