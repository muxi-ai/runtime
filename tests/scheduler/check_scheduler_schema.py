#!/usr/bin/env python3
"""Check the current scheduler database schema."""

import os
from sqlalchemy import create_engine, text, inspect


def check_schema():
    """Check the current database schema for scheduled_jobs table."""
    db_url = os.environ.get("POSTGRES_DATABASE_URL", "postgresql://localhost/muxi_framework")
    
    print("Checking scheduler database schema...")
    print("=" * 60)
    
    try:
        engine = create_engine(db_url)
    except Exception as e:
        print(f"❌ Failed to create database engine: {type(e).__name__}: {e}")
        print(f"   Database URL: {db_url}")
        return
    
    try:
        with engine.connect() as conn:
            # Check if scheduled_jobs table exists
            try:
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
            except Exception as e:
                print(f"❌ Failed to check if scheduled_jobs table exists: {type(e).__name__}: {e}")
                return

            if table_exists:
                # Get column information
                try:
                    inspector = inspect(engine)
                    columns = inspector.get_columns("scheduled_jobs")

                    print("\nColumns in scheduled_jobs table:")
                    print("-" * 60)
                    for col in columns:
                        print(f"  {col['name']:30} {col['type']}")
                except Exception as e:
                    print(f"❌ Failed to get column information: {type(e).__name__}: {e}")

                # Check for existing indexes
                try:
                    indexes = inspector.get_indexes("scheduled_jobs")
                    print("\nExisting indexes:")
                    print("-" * 60)
                    for idx in indexes:
                        print(f"  {idx['name']}")
                except Exception as e:
                    print(f"❌ Failed to get index information: {type(e).__name__}: {e}")

                # Check for existing constraints
                try:
                    constraints = inspector.get_check_constraints("scheduled_jobs")
                    print("\nExisting constraints:")
                    print("-" * 60)
                    for constraint in constraints:
                        print(f"  {constraint['name']}")
                except Exception as e:
                    print(f"❌ Failed to get constraint information: {type(e).__name__}: {e}")

                # Check if audit tables exist
                try:
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
                except Exception as e:
                    print(f"❌ Failed to check scheduled_job_audit_log table: {type(e).__name__}: {e}")

                try:
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
                except Exception as e:
                    print(f"❌ Failed to check scheduled_job_executions table: {type(e).__name__}: {e}")
                    
    except Exception as e:
        print(f"❌ Failed to connect to database: {type(e).__name__}: {e}")
        print(f"   Database URL: {db_url}")
        print("\nCommon causes:")
        print("  - Database server is not running")
        print("  - Incorrect database URL or credentials")
        print("  - Network connectivity issues")
        print("  - Database 'muxi_framework' does not exist")


if __name__ == "__main__":
    check_schema()
