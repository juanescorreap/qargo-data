"""
Moves every .wasm file that exceeds the Cloudflare Pages 25 MiB per-file limit
from the build directory to an R2 bucket, patches the absolute path references
in all JS bundles so the browser fetches from R2, then deletes the oversized
file so Pages deployment succeeds.

Usage (CI):
    R2_PUBLIC_URL=https://pub-xxx.r2.dev python ci/r2_offload.py

Options:
    --build-dir   Path to the built static site (default: dashboard/.evidence/template/build)
    --bucket      R2 bucket name (default: qargo-assets)
"""

import argparse
import os
import pathlib
import subprocess
import sys

PAGES_LIMIT_BYTES = 25 * 1024 * 1024  # Cloudflare Pages hard limit: 25 MiB per file


def offload(
    build_dir: pathlib.Path,
    r2_base: str,
    bucket: str = "qargo-assets",
) -> list[str]:
    """Upload every oversized WASM to R2, patch JS references, delete from build.

    Returns a list of WASM filenames that were offloaded.
    """
    offloaded: list[str] = []

    for wasm in sorted(build_dir.rglob("*.wasm")):
        size = wasm.stat().st_size
        if size <= PAGES_LIMIT_BYTES:
            print(f"OK  {wasm.name}  ({size / 1024 / 1024:.1f} MiB)")
            continue

        rel = wasm.relative_to(build_dir)
        rel_path = "/" + "/".join(rel.parts)  # e.g. /_app/immutable/assets/duckdb-eh.HASH.wasm
        r2_key = wasm.name
        r2_url = f"{r2_base.rstrip('/')}/{r2_key}"

        print(f"Upload  {rel}  ({size / 1024 / 1024:.1f} MiB)  ->  {r2_url}")
        subprocess.run(
            [
                "npx",
                "wrangler@3.112.0",
                "r2",
                "object",
                "put",
                f"{bucket}/{r2_key}",
                "--file",
                str(wasm),
                "--content-type",
                "application/wasm",
            ],
            check=True,
        )

        patched = 0
        for js in build_dir.rglob("*.js"):
            try:
                text = js.read_text("utf-8")
            except Exception:
                continue
            if rel_path not in text:
                continue
            js.write_text(text.replace(rel_path, r2_url), "utf-8")
            patched += 1

        print(f"  Patched {patched} JS file(s) to reference R2 URL")
        wasm.unlink()
        print(f"  Deleted {rel} from build dir")
        offloaded.append(wasm.name)

    return offloaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Offload oversized WASM files to Cloudflare R2")
    parser.add_argument(
        "--build-dir",
        default="dashboard/.evidence/template/build",
        type=pathlib.Path,
        help="Path to the Evidence build output directory",
    )
    parser.add_argument(
        "--bucket",
        default="qargo-assets",
        help="Cloudflare R2 bucket name",
    )
    args = parser.parse_args()

    r2_base = os.environ.get("R2_PUBLIC_URL", "")
    if not r2_base:
        sys.exit("Error: R2_PUBLIC_URL environment variable is not set")

    offload(args.build_dir, r2_base, args.bucket)


if __name__ == "__main__":
    main()
