#!/usr/bin/env python3
"""Smoke test: Migración."""

import asyncio, httpx, json


async def test_migration():
    # Test load balancer
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get("http://localhost:8087/health")
            lb_status = "pass" if resp.status_code == 200 else "fail"
        except:
            lb_status = "fail"

        # Test 8084 y 8085 directamente
        try:
            resp_8084 = await client.get("http://localhost:8084/health")
            status_8084 = "pass" if resp_8084.status_code == 200 else "fail"
        except:
            status_8084 = "fail"

        try:
            resp_8085 = await client.get("http://localhost:8085/health")
            status_8085 = "pass" if resp_8085.status_code == 200 else "fail"
        except:
            status_8085 = "fail"

    return {
        "load_balancer": lb_status,
        "backend_8084": status_8084,
        "backend_8085": status_8085,
        "status": "pass"
        if all([lb_status == "pass", status_8084 == "pass", status_8085 == "pass"])
        else "fail",
    }


async def main():
    result = await test_migration()

    with open("smoke_migration.json", "w") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    print(f"\n{'✅' if result['status'] == 'pass' else '❌'} Migration setup")


if __name__ == "__main__":
    asyncio.run(main())
