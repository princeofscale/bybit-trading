import asyncio
import sys
from pathlib import Path

from journal.report import SessionReport


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze_session.py <journal.db> [session_id]")
        print("\nIf session_id is not provided, will attempt to use the most recent session.")
        sys.exit(1)

    journal_path = Path(sys.argv[1])
    if not journal_path.exists():
        print(f"Error: Journal file not found: {journal_path}")
        sys.exit(1)

    session_id = sys.argv[2] if len(sys.argv) > 2 else ""

    if not session_id:
        from journal.reader import JournalReader
        from sqlalchemy import select, func
        from journal.models import SignalRecord

        reader = JournalReader(journal_path)
        await reader.initialize()

        if reader._session_factory:
            async with reader._session_factory() as session:
                stmt = select(SignalRecord.session_id, func.max(SignalRecord.timestamp)).group_by(
                    SignalRecord.session_id,
                ).order_by(func.max(SignalRecord.timestamp).desc()).limit(1)

                result = await session.execute(stmt)
                row = result.first()
                if row:
                    session_id = row[0]

        await reader.close()

        if not session_id:
            print("Error: No sessions found in journal")
            sys.exit(1)

        print(f"Using most recent session: {session_id}\n")

    report = SessionReport(journal_path)
    await report.initialize()

    result = await report.generate(session_id)

    print("=" * 60)
    print(f"SESSION REPORT: {session_id}")
    print("=" * 60)

    print("\n--- TRADE STATISTICS ---")
    for key, value in result["trade_stats"].items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    print("\n--- RISK SUMMARY ---")
    for key, value in result["risk_summary"].items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    print("\n--- EXECUTION QUALITY ---")
    for key, value in result["execution_quality"].items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    print("\n--- EQUITY CURVE ---")
    for key, value in result["equity_curve"].items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")

    print("\n--- PER-STRATEGY BREAKDOWN ---")
    for strategy_name, stats in result["per_strategy"].items():
        print(f"\n  {strategy_name}:")
        for key, value in stats.items():
            if isinstance(value, float):
                print(f"    {key}: {value:.4f}")
            else:
                print(f"    {key}: {value}")

    print("\n" + "=" * 60)

    await report.close()


if __name__ == "__main__":
    asyncio.run(main())
