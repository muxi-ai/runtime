#!/usr/bin/env python3
"""
Credential Key Rotation Utility

This script rotates encryption keys/salts for user credentials stored in the database.
It decrypts credentials with the old salt, re-encrypts with the new salt, and updates
the database in a transaction.

Usage:
    python utils/rotate_credential_keys.py \
        --formation-id myformation \
        --old-salt "old-salt-value" \
        --new-salt "new-salt-value" \
        [--db-url DATABASE_URL] \
        [--dry-run]

Example:
    # Dry run (show what would be changed without committing)
    python utils/rotate_credential_keys.py \
        --formation-id production-formation \
        --old-salt "muxi-user-credentials-salt-v1" \
        --new-salt "production-salt-2025" \
        --dry-run

    # Actual rotation (use your actual database URL)
    python utils/rotate_credential_keys.py \
        --formation-id production-formation \
        --old-salt "muxi-user-credentials-salt-v1" \
        --new-salt "production-salt-2025" \
        --db-url "$DATABASE_URL"
"""

import argparse
import asyncio
import sys
from datetime import datetime
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])

from src.muxi.services.db import DatabaseManager
from src.muxi.formation.credentials.encrypted import EncryptedCredentialResolver


async def rotate_credentials(
    formation_id: str,
    old_salt: str,
    new_salt: str,
    db_url: str,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Rotate credential encryption salt for all users.
    
    Args:
        formation_id: Formation identifier
        old_salt: Current salt value
        new_salt: New salt value to use
        db_url: Database connection URL
        dry_run: If True, show changes without committing
    
    Returns:
        Dictionary with rotation statistics
    """
    print(f"\n{'='*60}")
    print("CREDENTIAL KEY ROTATION")
    print(f"{'='*60}")
    print(f"Formation ID: {formation_id}")
    print(f"Old Salt: {old_salt}")
    print(f"New Salt: {new_salt}")
    print(f"Database: {db_url}")
    print(f"Mode: {'DRY RUN (no changes will be saved)' if dry_run else 'LIVE (changes will be committed)'}")
    print(f"{'='*60}\n")

    # Initialize database manager
    db_manager = DatabaseManager(db_url)
    
    # Create credential resolvers with old and new salts
    old_resolver = EncryptedCredentialResolver(
        async_session_maker=db_manager.AsyncSession,
        formation_id=formation_id,
        encryption_salt=old_salt,
    )
    
    new_resolver = EncryptedCredentialResolver(
        async_session_maker=db_manager.AsyncSession,
        formation_id=formation_id,
        encryption_salt=new_salt,
    )
    
    stats = {
        "users_processed": 0,
        "credentials_rotated": 0,
        "errors": [],
        "start_time": datetime.now(),
    }
    
    try:
        # Get all unique users with credentials
        async with db_manager.get_async_session() as session:
            from sqlalchemy import select, distinct
            from src.muxi.services.memory.models import Credentials
            
            # Query distinct user_ids
            stmt = select(distinct(Credentials.user_id)).where(
                Credentials.formation_id == formation_id
            )
            result = await session.execute(stmt)
            user_ids = [row[0] for row in result.all()]
            
            print(f"Found {len(user_ids)} users with credentials\n")
            
            for user_id in user_ids:
                print(f"Processing user: {user_id}")
                stats["users_processed"] += 1
                
                try:
                    # Get all credentials for this user using old salt
                    old_credentials = await old_resolver.get_all(user_id)
                    
                    if not old_credentials:
                        print("  No credentials found")
                        continue
                    
                    print(f"  Found {len(old_credentials)} credential(s)")
                    
                    # Re-encrypt each credential with new salt
                    for service, cred_data in old_credentials.items():
                        print(f"    Rotating: {service}")
                        
                        if not dry_run:
                            # Store with new salt (this will encrypt with new salt)
                            await new_resolver.store(user_id, service, cred_data)
                        
                        stats["credentials_rotated"] += 1
                    
                    print("  ✓ Completed")
                    
                except Exception as e:
                    error_msg = f"Error processing user {user_id}: {str(e)}"
                    print(f"  ✗ {error_msg}")
                    stats["errors"].append(error_msg)
                    
                    if not dry_run:
                        # In live mode, fail fast to avoid partial rotation
                        raise Exception(f"Rotation failed for user {user_id}: {e}")
            
            if not dry_run:
                # Commit the transaction
                await session.commit()
                print("\n✓ Changes committed to database")
            else:
                print("\n✓ Dry run complete (no changes saved)")
    
    finally:
        stats["end_time"] = datetime.now()
        stats["duration_seconds"] = (stats["end_time"] - stats["start_time"]).total_seconds()
        
        # Close database connections
        await db_manager.close_async()
    
    return stats


def print_summary(stats: Dict[str, Any], dry_run: bool):
    """Print rotation summary."""
    print(f"\n{'='*60}")
    print("ROTATION SUMMARY")
    print(f"{'='*60}")
    print(f"Users Processed: {stats['users_processed']}")
    print(f"Credentials Rotated: {stats['credentials_rotated']}")
    print(f"Errors: {len(stats['errors'])}")
    print(f"Duration: {stats['duration_seconds']:.2f} seconds")
    
    if stats['errors']:
        print("\nErrors encountered:")
        for error in stats['errors']:
            print(f"  - {error}")
    
    if dry_run:
        print("\n⚠️  DRY RUN MODE - No changes were saved to the database")
        print("    To perform actual rotation, run again without --dry-run")
    else:
        print("\n✓ Rotation completed successfully!")
    
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Rotate encryption salt for user credentials",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--formation-id",
        required=True,
        help="Formation identifier"
    )
    
    parser.add_argument(
        "--old-salt",
        required=True,
        help="Current salt value"
    )
    
    parser.add_argument(
        "--new-salt",
        required=True,
        help="New salt value to use"
    )
    
    parser.add_argument(
        "--db-url",
        help="Database connection URL (default: from environment)",
        default=None
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without committing"
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if args.old_salt == args.new_salt:
        print("Error: old-salt and new-salt must be different")
        sys.exit(1)
    
    # Confirm if not dry run
    if not args.dry_run:
        print("\n⚠️  WARNING: This will modify credentials in the database!")
        print(f"   Formation: {args.formation_id}")
        print(f"   Database: {args.db_url or '(from environment)'}")
        response = input("\nAre you sure you want to continue? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted.")
            sys.exit(0)
    
    # Run rotation
    try:
        stats = asyncio.run(rotate_credentials(
            formation_id=args.formation_id,
            old_salt=args.old_salt,
            new_salt=args.new_salt,
            db_url=args.db_url,
            dry_run=args.dry_run
        ))
        
        print_summary(stats, args.dry_run)
        
        # Exit with error code if there were errors
        if stats['errors']:
            sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n\nAborted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Rotation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
