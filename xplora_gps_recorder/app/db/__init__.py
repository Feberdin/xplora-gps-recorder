"""
Purpose: Namespace for database models, sessions, and migrations.
Inputs: Imported by services, scripts, and Alembic.
Outputs: Package marker only.
Invariants: Models should be imported from `app.db.models` to keep metadata complete.
Debugging: If tables are missing, confirm `Base.metadata` sees the model modules.
"""
