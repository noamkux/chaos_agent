"""Restoring what an earlier run left changed. Every undo still pending in undo_actions, from any run,
runs before a new run touches anything: a crash in the middle of an experiment leaves its undo pending
(it is written before the change), and this is where it is finally run."""
import json

from storage import db
import mcp_client


def already_restored(name, content):
    """True if an undo failed only because its change was already undone before the crash:
    restore_snapshot deletes its snapshot only after the object was put back, so a snapshot that
    no longer exists was restored."""
    text = str(content)
    return name == "disrupt__restore_snapshot" and "read snapshot" in text and "404" in text


async def restore_pending(conn, run_id, server_tools, scope):
    """Run every pending undo, oldest first, recorded as steps of this run, and mark each done.
    An undo that fails stays pending, so the next start tries it again, and the run does not start.
    Returns the steps."""
    steps = []
    failed = []
    for undo_id, from_run, action in db.pending_undos(conn):
        name, args = action["tool"], action["args"]
        if name not in server_tools:
            failed.append(f"undo {undo_id} of run {from_run} needs {name}, which this run does not load")
            continue
        output = json.loads(await mcp_client.call_tool(conn, run_id, server_tools, scope, name, args))
        steps.append(output["step"])
        if output["is_error"] and not already_restored(name, output["content"]):
            failed.append(f"undo {undo_id} of run {from_run} ({name} {args}): {output['content']}")
            continue
        db.finish_undo(conn, undo_id, "done")
    if failed:
        raise RuntimeError("an earlier run left changes that could not be undone, so this run does not "
                           "start; fix them, then start again: " + "; ".join(failed))
    return steps
