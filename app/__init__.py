"""
Purpose: Mark `app` as the top-level package for the recorder service.
Inputs: Imported by Python when the application, tests, or Alembic modules load package code.
Outputs: Package metadata only.
Invariants: Keep this module side-effect free so imports stay predictable.
Debugging: If imports fail, verify the repository root is on `PYTHONPATH`.
"""
