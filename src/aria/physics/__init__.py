"""ARIA physics pods (see docs/PHYSICS_COMPLETENESS_PLAN.md).

Each subpackage corresponds to one of the 14 domain pods from the
52-expert plan. Modules here implement the equations documented in
the matching scope note under `aria-core/docs/pods/`.

Rules (enforced by CLAUDE.md):
- every numerical constant carries a published citation on-line;
- every equation is derived in the scope note, not only the final form;
- every new module ships with the verification test cases named in §9
  of its scope note.
"""
