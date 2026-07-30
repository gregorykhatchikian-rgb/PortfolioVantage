"""Phase 0 verification: prove NVIDIA NIM connectivity before anything else is built.

Checks, in order:
  1. .env is gitignored (secrets can't be committed by accident)
  2. NVIDIA_API_KEY is present and not a placeholder
  3. NVIDIA actually accepts the key (a rejected key stops the run here - the catalog
     endpoint in step 4 answers without credentials, so it can't stand in for this)
  4. The configured model id actually exists in the live build.nvidia.com catalog
  5. A single hardcoded prompt returns a non-empty, error-free completion

Prints PASS/FAIL per check. Raw API output is only shown when something fails.
Exit code 0 = all passed, 1 = at least one failure.

Run:  python scripts/verify_phase0.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402

PROMPT = "Reply with exactly the word: CONNECTED"

failures: list[str] = []


def report(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(name)
    return ok


def check_gitignore() -> bool:
    gitignore = config.PROJECT_ROOT / ".gitignore"
    if not gitignore.exists():
        return report("secrets: .env is gitignored", False, ".gitignore not found")
    ignored = ".env" in gitignore.read_text().split()
    return report(
        "secrets: .env is gitignored",
        ignored,
        "" if ignored else "add '.env' to .gitignore before committing",
    )


def check_key() -> bool:
    try:
        key = config.require_nvidia_key()
    except config.MissingKeyError as exc:
        return report("NVIDIA_API_KEY present", False, str(exc))

    ok = report("NVIDIA_API_KEY present", True, config.mask(key))
    if not key.startswith("nvapi-"):
        # Not a hard failure - the prefix is a convention, not a guarantee - but a
        # 36-char UUID here is almost always an NGC org/account id pasted by mistake.
        print(
            f"       WARN: key does not start with 'nvapi-' (length {len(key)}). "
            "Inference keys from build.nvidia.com do. Check you copied the key from "
            "'Get API Key' on a model page, not an account or org identifier."
        )
    return ok


def check_auth(client) -> bool:
    """Smallest possible authenticated call, so a bad key fails here and not five lines down.

    Only 401/403 counts as an auth failure. A 404 or unknown-model error means the
    server accepted the credentials and got as far as model lookup, which is what
    this check cares about - the model id itself is check_model_exists's job.
    """
    try:
        client.chat.completions.create(
            model=config.NVIDIA_MODEL,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
            temperature=0,
        )
    except Exception as exc:  # noqa: BLE001
        status = getattr(exc, "status_code", None)
        if status in (401, 403):
            return report(
                "API key accepted by NVIDIA",
                False,
                f"{status} Unauthorized - the key in .env was rejected. Generate a new "
                "one at https://build.nvidia.com (open a model page -> Get API Key).",
            )
        if status == 429:
            return report(
                "API key accepted by NVIDIA", True, "429 rate limited, but credentials are valid"
            )
        # Any other error is not an auth verdict - let the later checks characterise it.
        return report("API key accepted by NVIDIA", True, f"no auth rejection ({type(exc).__name__})")

    return report("API key accepted by NVIDIA", True)


def check_model_exists(client) -> bool:
    """Catalog membership check - the model list on build.nvidia.com changes over time."""
    try:
        available = {m.id for m in client.models.list().data}
    except Exception as exc:  # noqa: BLE001 - surface the real error verbatim
        return report("model catalog reachable", False, f"{type(exc).__name__}: {exc}")

    # Note: this endpoint answers without valid credentials, so it says nothing about
    # the key. check_auth above is what validates that.
    report("model catalog reachable (unauthenticated)", True, f"{len(available)} models listed")
    ok = config.NVIDIA_MODEL in available
    if not ok:
        suggestions = sorted(m for m in available if "llama" in m or "nemotron" in m)[:8]
        return report(
            f"model '{config.NVIDIA_MODEL}' exists",
            False,
            "not in catalog. Similar ids available:\n    " + "\n    ".join(suggestions),
        )
    return report(f"model '{config.NVIDIA_MODEL}' exists", True)


def check_completion(client) -> bool:
    try:
        resp = client.chat.completions.create(
            model=config.NVIDIA_MODEL,
            messages=[{"role": "user", "content": PROMPT}],
            max_tokens=16,
            temperature=0,
        )
    except Exception as exc:  # noqa: BLE001
        hint = ""
        if "429" in str(exc):
            hint = " (rate limited - wait before retrying, do not loop)"
        return report("test completion returns content", False, f"{type(exc).__name__}: {exc}{hint}")

    if not resp.choices:
        return report("test completion returns content", False, f"no choices in response: {resp}")

    content = (resp.choices[0].message.content or "").strip()
    if not content:
        return report("test completion returns content", False, f"empty content. Raw: {resp}")

    return report("test completion returns content", True, f'model said: "{content}"')


def main() -> int:
    print("Phase 0 verification - NVIDIA NIM connectivity\n")

    check_gitignore()

    if not check_key():
        print("\nRESULT: FAIL - cannot continue without a real API key.")
        return 1

    try:
        from openai import OpenAI
    except ImportError:
        report("openai SDK installed", False, "run: pip install -r requirements.txt")
        print("\nRESULT: FAIL")
        return 1

    client = OpenAI(base_url=config.NVIDIA_BASE_URL, api_key=config.require_nvidia_key())

    if not check_auth(client):
        # Everything downstream is meaningless with a rejected key - don't run it and
        # don't imply partial progress.
        print("\nRESULT: FAIL - the API key was rejected. Fix that before rerunning.")
        return 1

    if check_model_exists(client):
        check_completion(client)

    print()
    if failures:
        print(f"RESULT: FAIL - {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("RESULT: PASS - all Phase 0 checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
