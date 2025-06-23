#!/usr/bin/env python3
"""Check the current scheduler database schema."""

import os
from sqlalchemy import create_engine, text, inspect


def check_schema():
    """Check the current database schema for scheduled_jobs table."""
    db_url = os.environ.get("POSTGRES_DATABASE_URL", "postgresql://ran@127.0.0.1/muxi_framework")
    engine = create_engine(db_url)

    print("Checking scheduler database schema...")
    print("=" * 60)

    with engine.connect() as conn:
        # Check if scheduled_jobs table exists
        result = conn.execute(
            text(
                """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'scheduled_jobs'
            );
        """
            )
        )

        table_exists = result.scalar()
        print(f"scheduled_jobs table exists: {table_exists}")

        if table_exists:
            # Get column information
            inspector = inspect(engine)
            columns = inspector.get_columns("scheduled_jobs")

            print("\nColumns in scheduled_jobs table:")
            print("-" * 60)
            for col in columns:
                print(f"  {col['name']:30} {col['type']}")

            # Check for existing indexes
            indexes = inspector.get_indexes("scheduled_jobs")
            print("\nExisting indexes:")
            print("-" * 60)
            for idx in indexes:
                print(f"  {idx['name']}")

            # Check for existing constraints
            constraints = inspector.get_check_constraints("scheduled_jobs")
            print("\nExisting constraints:")
            print("-" * 60)
            for constraint in constraints:
                print(f"  {constraint['name']}")

            # Check if audit tables exist
            audit_result = conn.execute(
                text(
                    """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'scheduled_job_audit_log'
                );
            """
                )
            )
            audit_exists = audit_result.scalar()
            print(f"\nscheduled_job_audit_log table exists: {audit_exists}")

            exec_result = conn.execute(
                text(
                    """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'scheduled_job_executions'
                );
            """
                )
            )
            exec_exists = exec_result.scalar()
            print(f"scheduled_job_executions table exists: {exec_exists}")


if __name__ == "__main__":
    check_schema()
