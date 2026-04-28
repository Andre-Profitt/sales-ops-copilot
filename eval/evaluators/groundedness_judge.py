"""LLM-as-judge groundedness evaluator (gpt53chat on apro-openai).

Sends the agent's brief plus the verified facts to the same Azure OpenAI
deployment used by brief.py and asks the model to flag any claims in the
brief that contradict or aren't supported by the facts.

Phase 3 deferred: replace this with `azure-ai-evaluation`'s
`GroundednessEvaluator` running inside an AI Foundry project so results land
in Foundry's eval dashboard.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any

from azure.identity import AzureCliCredential
from openai import AzureOpenAI


# Mirror brief.py / agent.py auth config exactly.
OPENAI_ENDPOINT = "https://apro-openai.openai.azure.com/"
OPENAI_API_VERSION = "2025-04-01-preview"
DEFAULT_MODEL = "gpt53chat"


JUDGE_SYSTEM = (
    "You are a strict fact-checking judge for a daily Sales Operations brief at SimCorp. "
    "You are given (1) a verified ground-truth facts dict and (2) the brief markdown. "
    "Your job: identify any claim in the brief that DIRECTLY CONTRADICTS the facts. "
    "The facts dict is a partial reference — it covers headline metrics, not every "
    "number in the brief. Claims about quantities NOT present in the facts dict are "
    "NEITHER grounded NOR ungrounded — ignore them. Only flag claims that conflict "
    "with a fact that IS present.\n\n"
    "SimCorp metric rules you MUST enforce regardless:\n"
    "- Land + Expand deals are reported in ARR (APTS_Opportunity_ARR__c).\n"
    "- Renewal deals are reported in ACV (APTS_Renewal_ACV__c).\n"
    "- ARR and ACV must NEVER be summed or blended.\n"
    "- Every dollar figure must be labelled either ARR or ACV. Flag any blended or "
    "  unlabelled dollar figure.\n\n"
    "Tolerance: dollar figures may differ by up to ±5% from the facts (the pipeline "
    "moves daily). Counts (alert counts, deal counts) must match exactly. Names and "
    "labels must match exactly.\n\n"
    "Return ONLY a JSON object with this schema:\n"
    "{\n"
    '  "ungrounded_claims": [string, ...],\n'
    '  "score": number between 0 and 1,\n'
    '  "rationale": string\n'
    "}\n"
    "score=1.0 means no claim contradicts the facts. score=0.0 means the brief "
    "contradicts the facts in load-bearing ways. No prose outside the JSON object."
)


@dataclass
class GroundednessResult:
    score: float
    ungrounded_claims: list[str] = field(default_factory=list)
    rationale: str = ""
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GroundednessLLMJudgeEvaluator:
    """LLM-judge groundedness scorer against a verified facts dict."""

    name = "GroundednessLLMJudgeEvaluator"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        endpoint: str = OPENAI_ENDPOINT,
        api_version: str = OPENAI_API_VERSION,
        max_completion_tokens: int = 4000,
    ) -> None:
        self.model = model
        self.endpoint = endpoint
        self.api_version = api_version
        self.max_completion_tokens = max_completion_tokens

    def _client(self) -> AzureOpenAI:
        cred = AzureCliCredential()
        token_provider = lambda: cred.get_token(
            "https://cognitiveservices.azure.com/.default"
        ).token
        return AzureOpenAI(
            azure_endpoint=self.endpoint,
            azure_ad_token_provider=token_provider,
            api_version=self.api_version,
        )

    def run(self, facts: dict[str, Any], brief_md: str) -> GroundednessResult:
        client = self._client()
        user_msg = (
            "VERIFIED FACTS (JSON):\n```json\n"
            + json.dumps(facts, indent=2)
            + "\n```\n\nBRIEF MARKDOWN:\n```markdown\n"
            + brief_md
            + "\n```\n\nReturn the JSON judgement now."
        )

        # GPT-5.x rejects non-default temperature; do not set it.
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            max_completion_tokens=self.max_completion_tokens,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> GroundednessResult:
        text = raw.strip()
        # Strip ```json fences if the model added them despite response_format
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return GroundednessResult(
                score=0.0,
                ungrounded_claims=["judge returned non-JSON"],
                rationale="parse error",
                raw=raw,
            )
        score = float(data.get("score", 0.0))
        score = max(0.0, min(1.0, score))
        return GroundednessResult(
            score=score,
            ungrounded_claims=list(data.get("ungrounded_claims") or []),
            rationale=str(data.get("rationale") or ""),
            raw=raw,
        )
