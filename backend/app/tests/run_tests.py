"""
Standalone Test Runner for SkillSync Backend Tests.
Runs all async test functions without requiring external test runner packages.
"""
import asyncio
import inspect
import pathlib
import sys
import time

backend_dir = pathlib.Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import Base, engine
from app.tests import (
    test_api,
    test_github_analysis,
    test_ai_engine,
    test_database_persistence,
    test_webhooks,
    test_qa_security,
    test_gap_solver,
    test_evidence_verification,
    test_phase_g_e2e_integration,
)


async def run_all_tests():
    print("=" * 65)
    print("SkillSync Complete Automated Test Suite (Phases 3 to 9)")
    print("=" * 65)

    # Disable verbose SQL logging and enable test doubles for isolated test run
    engine.echo = False
    from app.core.config import settings
    settings.use_test_doubles = True

    # 1. Setup test database with migrations
    from app.core.database import init_db
    await init_db()

    # 2. Collect test functions across modules
    test_functions = []
    for module in [
        test_api,
        test_github_analysis,
        test_ai_engine,
        test_database_persistence,
        test_webhooks,
        test_qa_security,
        test_gap_solver,
        test_evidence_verification,
        test_phase_g_e2e_integration,
    ]:
        for name, func in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("test_"):
                test_functions.append((name, func))




    print(f"Discovered {len(test_functions)} automated tests.\n")

    passed = 0
    failed = 0
    total_start = time.perf_counter()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        for name, func in test_functions:
            start = time.perf_counter()
            try:
                sig = inspect.signature(func)
                call_args = [client] if len(sig.parameters) == 1 else []
                if inspect.iscoroutinefunction(func):
                    await func(*call_args)
                else:
                    func(*call_args)
                elapsed = (time.perf_counter() - start) * 1000
                print(f"  [PASS] {name} ({elapsed:.1f}ms)")
                passed += 1
            except Exception as e:
                elapsed = (time.perf_counter() - start) * 1000
                print(f"  [FAIL] {name} ({elapsed:.1f}ms)")
                print(f"         Error: {type(e).__name__}: {str(e)}")
                failed += 1

    total_time = (time.perf_counter() - total_start) * 1000
    print("\n" + "=" * 65)
    print(f"Results: {passed} passed, {failed} failed in {total_time:.1f}ms")
    print("=" * 65)

    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
