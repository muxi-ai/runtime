"""
Credential seeder for 4d3 tests.

Ensures user1 has two GitHub credentials ("ranaroussi" and "lily automaze")
in the database. All 4d3 tests rely on this for multi-credential clarification.
"""

from sqlalchemy import text


async def ensure_dual_github_credentials(formation):
    """
    Ensure user1 has exactly two GitHub credentials: 'ranaroussi' and 'lily automaze'.

    Uses direct SQL for setup because the EncryptedCredentialResolver's store_credential
    requires a fully initialized formation, and we need to clone the existing encrypted
    credential data (not re-encrypt with a different name, which would produce a different blob).

    Args:
        formation: A loaded Formation instance with _db_manager available.

    Returns:
        True if credentials are ready, False on error.
    """
    if not formation._db_manager:
        print("WARNING: No database manager available, cannot seed credentials")
        return False

    try:
        async with formation._db_manager.get_async_session() as session:
            # Get user1's internal ID
            result = await session.execute(
                text("SELECT user_id FROM user_identifiers WHERE identifier = :uid"),
                {"uid": "user1"},
            )
            row = result.fetchone()
            if not row:
                print("WARNING: user1 not found in user_identifiers")
                return False
            internal_user_id = row[0]

            # Get existing GitHub credentials for user1
            result = await session.execute(
                text("""
                    SELECT id, name, credentials FROM credentials
                    WHERE user_id = :uid AND service = 'github'
                    ORDER BY name
                """),
                {"uid": internal_user_id},
            )
            creds = result.fetchall()
            existing_names = {c[1] for c in creds}

            # Always clean up extras first (previous test runs may have added "github" entries)
            wanted = {"ranaroussi", "lily automaze"}
            for c in creds:
                if c[1] not in wanted:
                    await session.execute(
                        text("DELETE FROM credentials WHERE id = :id"),
                        {"id": c[0]},
                    )
                    print(f"  Cleaned up extra credential '{c[1]}' (id={c[0]})")

            if "ranaroussi" in existing_names and "lily automaze" in existing_names:
                await session.commit()
                print(f"Credentials already seeded: {sorted(wanted)}")
                return True

            if len(creds) == 0:
                print("WARNING: No GitHub credentials for user1 at all -- cannot seed")
                return False

            # Use the first existing credential's encrypted blob as template
            template_id = creds[0][0]
            template_blob = creds[0][2]

            # Rename the existing credential to "ranaroussi" if needed
            if creds[0][1] != "ranaroussi":
                await session.execute(
                    text("UPDATE credentials SET name = :name WHERE id = :id"),
                    {"name": "ranaroussi", "id": template_id},
                )
                print(f"  Renamed credential '{creds[0][1]}' -> 'ranaroussi'")

            # Add "lily automaze" if it doesn't exist
            if "lily automaze" not in existing_names:
                import nanoid
                await session.execute(
                    text("""
                        INSERT INTO credentials (user_id, credential_id, name, service, credentials, created_at)
                        VALUES (:uid, :cid, :name, 'github', :creds, NOW())
                    """),
                    {
                        "uid": internal_user_id,
                        "cid": nanoid.generate(),
                        "name": "lily automaze",
                        "creds": template_blob,
                    },
                )
                print("  Added credential 'lily automaze'")

            await session.commit()

            # Verify
            result = await session.execute(
                text("""
                    SELECT name FROM credentials
                    WHERE user_id = :uid AND service = 'github'
                    ORDER BY name
                """),
                {"uid": internal_user_id},
            )
            final = [r[0] for r in result.fetchall()]
            print(f"Credentials ready: {final}")
            return len(final) == 2

    except Exception as e:
        print(f"ERROR seeding credentials: {e}")
        import traceback
        traceback.print_exc()
        return False
