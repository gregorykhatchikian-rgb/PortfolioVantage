"""Phase 3: turn one earnings call transcript into structured JSON via an LLM.

The contract is narrow on purpose: transcript in, one validated dict out, or a
result carrying the reason it failed. Nothing here retries forever, invents a
score, or returns a half-filled object - a caller that gets ok=True can trust
every field.

Two things this guards against, both of which look like success at a glance:
  - models wrapping JSON in ```json fences, which json.loads rejects
  - models returning a well-formed object with a sentiment_score of 2.5, or a
    themes list that's a single comma-joined string
"""

import json
import re
import time
from dataclasses import dataclass, field

from openai import OpenAI
from openai import APIStatusError, APITimeoutError, APIConnectionError

from src import config
from src.transcript_fetcher import Transcript

REQUIRED_FIELDS = (
    "ticker", "quarter", "sentiment_score", "sentiment_label",
    "themes", "notable_shift", "confidence",
)
VALID_CONFIDENCE = {"low", "medium", "high"}
# Closed set: free-text labels drifted into echoing the scoring rubric verbatim
# ("unambiguous strength"), which would have shipped straight to the dashboard.
VALID_LABELS = {"very confident", "confident", "steady", "cautious",
                "defensive", "alarmed"}

# Long enough for the whole object, short enough that a rambling model gets cut
# off rather than burning quota.
MAX_OUTPUT_TOKENS = 700
MAX_RETRIES = 2  # plan.md: back off, don't hammer a rate-limited endpoint

# A NIM model can accept a request and then never generate (observed on
# llama-3.3-70b). Without a bound, one hung call stalls a whole batch run.
REQUEST_TIMEOUT_SECONDS = 90.0

SYSTEM_PROMPT = """You are a sell-side analyst extracting structured signal from earnings call transcripts.

Return ONLY a JSON object. No preamble, no explanation, no markdown fences.

Schema:
{
  "ticker": string,
  "quarter": string,
  "sentiment_score": number from -1.0 to 1.0,
  "sentiment_label": EXACTLY one of: "very confident", "confident", "steady",
                     "cautious", "defensive", "alarmed". Use no other wording,
  "themes": array of 2-5 short lowercase noun phrases, e.g. ["margin pressure", "ai capex"],
  "notable_shift": one sentence on what changed in management's tone or emphasis,
  "confidence": "low" | "medium" | "high"
}

Scoring guidance (top and bottom bands are deliberately hard to reach):
  -1.0 to -0.65  guidance withdrawn or cut sharply; direct questions evaded
  -0.65 to -0.4  material deterioration; heavy hedging throughout
  -0.4 to  0.1   results mixed, or management raises concerns without resolving them
   0.1 to  0.4   results in line; nothing significant raised in either direction
   0.4 to  0.65  results beat expectations, but management raises real headwinds
   0.65 to 1.0   results beat AND guidance raised AND no material headwind raised

Most good quarters land in 0.4-0.65, not above it. A company can beat guidance and
still belong there. Reserve above 0.65 for calls where you cannot point to a
material concern management raised themselves.

Every material headwind management brings up on their own - supply constraints,
rising input costs, a softening segment, a cut outlook - pulls the score down,
even when headline results are strong. Repeated emphasis on a constraint is
evidence about tone, not incidental detail.

Judge tone and emphasis in management's own commentary, especially prepared
remarks and how directly they answer analyst questions. Hedging, deflection, and
newly-introduced caveats matter more than headline numbers.

Set "confidence" to "low" when the transcript is short, truncated, or the tone is
genuinely ambiguous. Do not pad it to look decisive."""


@dataclass
class ExtractionResult:
    ticker: str
    quarter: str
    ok: bool
    data: dict | None = None
    errors: list[str] = field(default_factory=list)
    raw_response: str = ""
    attempts: int = 0
    # Why each earlier attempt was rejected. Without this a silent retry hides
    # whether a failure was a one-off or a systematic prompt problem.
    retry_reasons: list[str] = field(default_factory=list)


# Score -> label, applied in code. Letting the model choose both allowed a 0.8
# score to arrive labelled "confident" while 0.7 arrived "very confident", which
# is the kind of inconsistency that undermines a dashboard. The score is the
# signal; the label is presentation derived from it.
LABEL_BANDS = (
    (-1.01, -0.65, "alarmed"),
    (-0.65, -0.40, "defensive"),
    (-0.40, 0.10, "cautious"),
    (0.10, 0.40, "steady"),
    (0.40, 0.65, "confident"),
    (0.65, 1.01, "very confident"),
)


def label_for_score(score: float) -> str:
    for low, high, label in LABEL_BANDS:
        if low <= score < high:
            return label
    return "steady"  # unreachable for a validated score, but never return None


def _client() -> OpenAI:
    # max_retries=0: retry/back-off is handled in extract(), so the SDK must not
    # silently multiply attempt behind our back.
    return OpenAI(base_url=config.NVIDIA_BASE_URL, api_key=config.require_nvidia_key(),
                  timeout=REQUEST_TIMEOUT_SECONDS, max_retries=0)


def strip_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers, then trim to the outermost JSON object.

    Models that are told 'no markdown' still emit it often enough that parsing
    without this step fails intermittently - the worst kind of bug to chase.
    """
    text = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    return text


def validate(obj: object, ticker: str, quarter: str) -> list[str]:
    """Return a list of problems. Empty list means the object is usable."""
    errors: list[str] = []

    if not isinstance(obj, dict):
        return [f"expected a JSON object, got {type(obj).__name__}"]

    for f in REQUIRED_FIELDS:
        if f not in obj:
            errors.append(f"missing field: {f}")

    score = obj.get("sentiment_score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        errors.append(f"sentiment_score is not a number: {score!r}")
    elif not -1.0 <= float(score) <= 1.0:
        errors.append(f"sentiment_score {score} outside -1.0..1.0")

    themes = obj.get("themes")
    if not isinstance(themes, list):
        errors.append(f"themes is not a list: {type(themes).__name__}")
    elif not themes:
        errors.append("themes is empty")
    elif not all(isinstance(t, str) and t.strip() for t in themes):
        errors.append(f"themes contains non-string or blank entries: {themes!r}")

    label = obj.get("sentiment_label")
    if not isinstance(label, str) or not label.strip():
        errors.append(f"sentiment_label is blank or not a string: {label!r}")
    elif label.strip().lower() not in VALID_LABELS:
        errors.append(f"sentiment_label {label!r} not one of {sorted(VALID_LABELS)}")

    shift = obj.get("notable_shift")
    if not isinstance(shift, str) or not shift.strip():
        errors.append("notable_shift is blank - it exists so the score can be sanity-checked")

    conf = obj.get("confidence")
    if not isinstance(conf, str) or conf.lower() not in VALID_CONFIDENCE:
        errors.append(f"confidence not one of {sorted(VALID_CONFIDENCE)}: {conf!r}")

    # The model echoes these back; a mismatch means it lost track of which call it
    # was reading, which would silently misfile the result downstream.
    if str(obj.get("ticker", "")).upper() != ticker.upper():
        errors.append(f"ticker mismatch: model said {obj.get('ticker')!r}, expected {ticker!r}")
    if quarter.replace(" ", "") not in str(obj.get("quarter", "")).replace(" ", ""):
        errors.append(f"quarter mismatch: model said {obj.get('quarter')!r}, expected {quarter!r}")

    return errors


def extract(transcript: Transcript, client: OpenAI | None = None,
            model: str | None = None, system_prompt: str | None = None) -> ExtractionResult:
    """Extract structured sentiment from one transcript. Never raises on model output."""
    client = client or _client()
    model = model or config.NVIDIA_MODEL

    user_prompt = (
        f"Ticker: {transcript.ticker}\n"
        f"Quarter: {transcript.quarter}\n\n"
        f"Earnings call transcript:\n\n{transcript.raw_text}"
    )

    result = ExtractionResult(ticker=transcript.ticker, quarter=transcript.quarter, ok=False)

    for attempt in range(1, MAX_RETRIES + 2):
        result.attempts = attempt
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,   # near-deterministic; this is extraction, not writing
                max_tokens=MAX_OUTPUT_TOKENS,
                response_format={"type": "json_object"},
            )
        except APIStatusError as exc:
            if exc.status_code == 429 and attempt <= MAX_RETRIES:
                result.retry_reasons.append(f"attempt {attempt}: rate limited (429)")
                time.sleep(5 * attempt)  # linear back-off, only twice
                continue
            result.errors = [f"API error {exc.status_code}: {exc}"]
            return result
        except (APITimeoutError, APIConnectionError) as exc:
            if attempt <= MAX_RETRIES:
                result.retry_reasons.append(f"attempt {attempt}: {type(exc).__name__}")
                time.sleep(2 * attempt)
                continue
            result.errors = [
                f"{type(exc).__name__} after {attempt} attempts: the model accepted the "
                f"request but did not generate. Try a different NVIDIA_MODEL."
            ]
            return result
        except Exception as exc:  # noqa: BLE001
            result.errors = [f"{type(exc).__name__}: {exc}"]
            return result

        raw = (resp.choices[0].message.content or "").strip()
        result.raw_response = raw

        try:
            parsed = json.loads(strip_fences(raw))
        except json.JSONDecodeError as exc:
            if attempt <= MAX_RETRIES:
                result.retry_reasons.append(f"attempt {attempt}: invalid JSON ({exc})")
                continue  # transient malformed output; one more try before giving up
            result.errors = [f"response was not valid JSON: {exc}"]
            return result

        errors = validate(parsed, transcript.ticker, transcript.quarter)
        if errors:
            if attempt <= MAX_RETRIES:
                result.retry_reasons.append(f"attempt {attempt}: {'; '.join(errors)}")
                continue
            result.errors = errors
            result.data = parsed if isinstance(parsed, dict) else None
            return result

        parsed["confidence"] = str(parsed["confidence"]).lower()
        model_label = str(parsed["sentiment_label"]).strip().lower()
        parsed["sentiment_label"] = label_for_score(float(parsed["sentiment_score"]))
        # Kept for QA: a persistent gap between the two suggests the model is
        # scoring and describing on different scales.
        parsed["model_label"] = model_label
        parsed["themes"] = [str(t).strip().lower() for t in parsed["themes"]]
        result.data, result.ok = parsed, True
        return result

    result.errors = result.errors or ["exhausted retries without a usable response"]
    return result
