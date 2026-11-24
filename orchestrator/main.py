"""Orchestrator entry point."""
import db


def main():
    with db.connect() as conn:
        db.apply_schema(conn)
    print("schema applied")


if __name__ == "__main__":
    main()