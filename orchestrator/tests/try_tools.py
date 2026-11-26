"""Manual check of tool filtering, scope enforcement and the audit trail."""
import asyncio
import db
import tools

ROE = {"scope": {"namespaces": ["boutique"]}}


async def main():
    with db.connect() as conn:
        run_id = db.create_run(conn, "boutique", "test", "observe", ROE, 1)
        db.claim_run(conn, run_id)

        available = await tools.load_tools("observe")
        allowed = {t["name"] for t in available}
        scope = ROE["scope"]["namespaces"]
        print("tools:", allowed)

        ok = await tools.call_tool(conn, run_id, allowed, scope, "observe__get_workloads", {"namespace": "boutique"})
        print("allowed call:", ok[:80], "...")
        print(await tools.call_tool(conn, run_id, allowed, scope, "observe__get_workloads", {"namespace": "kube-system"}))
        print(await tools.call_tool(conn, run_id, allowed, scope, "disrupt__scale_deployment", {"namespace": "boutique"}))

        rows = conn.execute(
            "SELECT step, name, allowed, output IS NOT NULL FROM steps WHERE run_id = %s ORDER BY step",
            (run_id,),
        )
        for row in rows:
            print(row)

        db.finish_run(conn, run_id, "completed")
        conn.execute("DELETE FROM steps WHERE run_id IN (SELECT id FROM runs WHERE model = 'test')")
        conn.execute("DELETE FROM runs WHERE model = 'test'")
        conn.commit()


asyncio.run(main())
