# Kiro Templates

> **Purpose:** Templates for creating Kiro specs in new projects

---

## What's Included

### **Steering Templates** (`.kiro/steering/`)

Define project-wide standards and principles:

- **product.md** - What the project is, what it does, target users, core principles
- **tech.md** - Technical standards, architecture patterns, code style, safety rules
- **structure.md** - Code organization, layer responsibilities, naming conventions

**Usage:** Copy to new projects, fill in project-specific details.

### **Spec Templates** (`.kiro/specs/FEATURE_NAME/`)

Define individual feature specifications:

- **requirements.md** - What needs to be built (functional, non-functional, constraints)
- **design.md** - How it will be built (architecture, data model, API design)
- **tasks.md** - Step-by-step implementation plan (phases, checkpoints, estimates)

**Usage:** Copy to `.kiro/specs/your-feature-name/`, customize for feature.

---

## Quick Start

### **Option A: Manual Setup**

1. **Copy templates to your project:**
   ```bash
   cp -r templates/.kiro /path/to/your-project/
   ```

2. **Customize steering docs:**
   - Edit `.kiro/steering/product.md` (replace placeholders)
   - Edit `.kiro/steering/tech.md` (add your tech standards)
   - Edit `.kiro/steering/structure.md` (define your structure)

3. **Create feature specs:**
   ```bash
   mkdir -p .kiro/specs/your-feature-name
   cp templates/.kiro/specs/FEATURE_NAME/* .kiro/specs/your-feature-name/
   # Edit each file for your feature
   ```

---

### **Option B: Automated Generation (RECOMMENDED!)**

Use the `generate_kiro_specs.py` script to automate spec creation:

```bash
python scripts/generate_kiro_specs.py \
    --project-root /path/to/your/project \
    --feature-name user-authentication \
    --description "JWT-based auth with refresh tokens and role-based access control"
```

**What it does:**
1. Creates `.kiro/specs/` and `.kiro/steering/` directories
2. Copies steering templates
3. Uses Kiro CLI to generate:
   - `requirements.md` based on feature description
   - `design.md` based on requirements
   - `tasks.md` based on requirements + design

**Benefits:**
- ✅ No pasting! Fully automated
- ✅ Kiro generates content specific to your feature
- ✅ Consistent structure across all specs
- ✅ Ready for immediate review/refinement

---

### **Option C: Pure CLI Workflow**

Use Kiro CLI directly (no GUI!):

```bash
# Kiro automatically reads .kiro/ files in your project

# Review architecture
kiro-cli chat --no-interactive "Review .kiro/specs/auth/design.md for security flaws"

# Generate tasks
kiro-cli chat --no-interactive "Based on .kiro/specs/auth/requirements.md, create a task breakdown"

# Ask specific questions
kiro-cli chat --no-interactive "What edge cases are missing from .kiro/specs/auth/?"
```

---

## Integration with Review System

Kiro specs can be reviewed via our multi-AI review system:

```bash
# Review requirements doc
python scaffold_cli.py review \
    --type document \
    --input .kiro/specs/auth/requirements.md \
    --round 1

# Review design doc (uses Kiro for Tier 1 architecture review!)
python scaffold_cli.py review \
    --type document \
    --input .kiro/specs/auth/design.md \
    --round 1
```

---

## Workflow: Tier 1 → Tier 2/3

### **Tier 1 (Kiro): Planning**

1. Create `.kiro/specs/feature-name/` using script or manual
2. Review with Kiro CLI: `kiro-cli chat --no-interactive "Review design.md"`
3. Refine based on feedback
4. Mark as ready for implementation

### **Tier 2/3 (DeepSeek/Cursor): Execution**

1. Read `.kiro/specs/feature-name/tasks.md`
2. Pick a specific task (e.g., "2.1 Implement data models")
3. Implement following `.kiro/steering/` standards
4. Mark task complete in tasks.md
5. Move to next task

---

## File Structure

```
project-root/
  .kiro/
    steering/              # Project-wide standards
      product.md           # Product principles
      tech.md              # Technical standards
      structure.md         # Code organization
    specs/                 # Feature specifications
      authentication/
        requirements.md    # What to build
        design.md          # How to build it
        tasks.md           # Step-by-step plan
      reporting/
        requirements.md
        design.md
        tasks.md
```

---

## Version Control

**YES! Commit `.kiro/` to git!**

```bash
git add .kiro/
git commit -m "Add Kiro specs for authentication feature"
```

**Benefits:**
- ✅ Team members see the same specs
- ✅ History of architecture decisions
- ✅ Easy to review changes
- ✅ AI assistants read from version-controlled specs

---

## Tips & Best Practices

### **Steering Docs**

- ✅ Fill them out **once** at project start
- ✅ Update when standards change
- ✅ Keep them concise (1-2 pages each)
- ✅ Link to detailed docs if needed

### **Spec Docs**

- ✅ One feature per spec directory
- ✅ Start with requirements, then design, then tasks
- ✅ Review each doc before moving to next
- ✅ Keep tasks actionable (< 4 hours each)

### **Automation**

- ✅ Use `generate_kiro_specs.py` for initial creation
- ✅ Use Kiro CLI for refinement
- ✅ Skip GUI unless you want visual organization

---

## Examples

See real examples in:
- **Tax Organizer** - Erik's actual Kiro specs (documented in KIRO_DEEP_DIVE.md)
- **Hologram Project** - Multi-round review process

---

## Troubleshooting

**Q: Kiro CLI not found**  
**A:** Install via `brew install kiro-cli`

**Q: Kiro doesn't see my `.kiro/` files**  
**A:** Make sure you're in the project directory when running `kiro-cli chat`

**Q: Generated specs are too generic**  
**A:** Provide more detailed feature description to `generate_kiro_specs.py`

---

**Last Updated:** December 23, 2025  
**Status:** Ready for production use! 🚀

