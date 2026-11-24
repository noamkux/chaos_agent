"""Manual check of the run lifecycle and the per-namespace lock."""
import db

ROE = {"scope": {"namespaces": ["boutique"]}}

with db.connect() as conn:
    first = db.create_run(conn, "boutique", "test", "observe", ROE, 1)
    second = db.create_run(conn, "boutique", "test", "observe", ROE, 1)

    print("claim first: ", db.claim_run(conn, first))
    print("claim second:", db.claim_run(conn, second))
    print("claim first again:", db.claim_run(conn, first))

    db.finish_run(conn, first, "completed")
    print("claim second after first finished:", db.claim_run(conn, second))

    db.finish_run(conn, second, "completed")
    conn.execute("DELETE FROM runs WHERE model = 'test'")
    conn.commit()