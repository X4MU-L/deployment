from __future__ import annotations

import argparse
import asyncio

import httpx

from app.celery_builder.runner import run_fake_build


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fake builder against a build id")
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:8000", help="Control-plane base URL"
    )
    parser.add_argument("--build-id", required=True, help="Build id to process")
    parser.add_argument(
        "--service-token",
        default="dev-internal-service-token",
        help="Internal service bearer token",
    )
    parser.add_argument("--service-name", default="fake-builder", help="Service name header")
    args = parser.parse_args()
    asyncio.run(_main(args))


async def _main(args: argparse.Namespace) -> None:
    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/")) as client:
        result = await run_fake_build(
            client,
            build_id=args.build_id,
            service_token=args.service_token,
            service_name=args.service_name,
        )
    print(result)


if __name__ == "__main__":
    main()
