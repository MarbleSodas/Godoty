"""Code Quality Evaluation Script.

Uses LLM-as-a-judge pattern to evaluate GDScript code quality.
Measures adherence to Godot 4.x best practices and type safety.

Based on Better Agents evaluation standards.

Usage:
    python -m tests.evaluations.code_quality_eval
    
    # With specific model
    python -m tests.evaluations.code_quality_eval --model gpt-4o
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path

EVAL_PROMPTS_DIR = Path(__file__).parent
PROJECT_ROOT = Path(__file__).parent.parent.parent


@dataclass
class EvalResult:
    scenario_name: str
    score: float
    max_score: float
    criteria_scores: dict[str, float]
    feedback: str
    passed: bool


@dataclass
class EvalScenario:
    name: str
    prompt: str
    expected_patterns: list[str]
    forbidden_patterns: list[str]
    criteria: dict[str, str]


GDSCRIPT_QUALITY_CRITERIA = {
    "type_safety": "All function parameters and return types have explicit type hints",
    "godot4_syntax": "Uses Godot 4.x patterns (signal.emit(), await, CharacterBody2D)",
    "style_guide": "Follows GDScript style (snake_case, PascalCase, @export/@onready)",
    "code_clarity": "Code is readable with meaningful names and proper structure",
    "error_handling": "Appropriate null checks and edge case handling",
}


EVAL_SCENARIOS: list[EvalScenario] = [
    EvalScenario(
        name="player_movement",
        prompt="Create a basic 2D player movement script for a platformer using CharacterBody2D",
        expected_patterns=[
            r"extends\s+CharacterBody2D",
            r":\s*(float|int|Vector2|String)",
            r"->\s*(void|float|int|Vector2|bool)",
            r"move_and_slide\(\)",
            r"@export",
        ],
        forbidden_patterns=[
            r"yield\s*\(",
            r"emit_signal\s*\(",
            r"KinematicBody",
            r"move_and_slide\s*\([^)]+\)",
        ],
        criteria=GDSCRIPT_QUALITY_CRITERIA,
    ),
    EvalScenario(
        name="signal_connection",
        prompt="Create a UI controller that connects button signals programmatically",
        expected_patterns=[
            r"\.connect\s*\(",
            r":\s*(Button|Control|Node)",
            r"@onready",
        ],
        forbidden_patterns=[
            r'connect\s*\(\s*"[^"]+"\s*,\s*\w+\s*,\s*"[^"]+"\s*\)',
        ],
        criteria=GDSCRIPT_QUALITY_CRITERIA,
    ),
    EvalScenario(
        name="custom_resource",
        prompt="Create a Resource-based item data class for an inventory system",
        expected_patterns=[
            r"extends\s+Resource",
            r"class_name\s+\w+",
            r"@export",
            r":\s*(String|int|float|Texture2D)",
        ],
        forbidden_patterns=[
            r"extends\s+Node",
            r"extends\s+Object",
        ],
        criteria=GDSCRIPT_QUALITY_CRITERIA,
    ),
]


JUDGE_SYSTEM_PROMPT = """You are an expert GDScript code reviewer evaluating AI-generated code.

Rate the code on each criterion from 0-10:
- 0-3: Poor, major issues
- 4-6: Acceptable, some issues
- 7-8: Good, minor issues
- 9-10: Excellent, meets all standards

Provide scores in this exact JSON format:
{
    "scores": {
        "type_safety": <0-10>,
        "godot4_syntax": <0-10>,
        "style_guide": <0-10>,
        "code_clarity": <0-10>,
        "error_handling": <0-10>
    },
    "feedback": "<brief overall feedback>"
}

Criteria definitions:
- type_safety: All function parameters and return types have explicit type hints
- godot4_syntax: Uses Godot 4.x patterns (signal.emit(), await, CharacterBody2D)
- style_guide: Follows GDScript style (snake_case, PascalCase, @export/@onready)
- code_clarity: Code is readable with meaningful names and proper structure
- error_handling: Appropriate null checks and edge case handling"""


def check_patterns(code: str, expected: list[str], forbidden: list[str]) -> tuple[int, int, list[str]]:
    """Check for expected and forbidden patterns in code."""
    issues = []
    expected_found = 0
    forbidden_found = 0

    for pattern in expected:
        if re.search(pattern, code, re.IGNORECASE):
            expected_found += 1
        else:
            issues.append(f"Missing expected pattern: {pattern}")

    for pattern in forbidden:
        if re.search(pattern, code, re.IGNORECASE):
            forbidden_found += 1
            issues.append(f"Found forbidden pattern: {pattern}")

    return expected_found, forbidden_found, issues


async def evaluate_with_llm(
    code: str,
    scenario: EvalScenario,
    model_id: str = "gpt-4o",
) -> dict:
    """Use LLM-as-judge to evaluate code quality."""
    try:
        from agno.models.litellm import LiteLLM
    except ImportError:
        return {
            "scores": {k: 5.0 for k in GDSCRIPT_QUALITY_CRITERIA},
            "feedback": "LLM evaluation skipped (agno not available)",
        }

    model = LiteLLM(id=f"openai/{model_id}")

    user_prompt = f"""Evaluate this GDScript code for the task: "{scenario.prompt}"

```gdscript
{code}
```

Provide your evaluation as JSON."""

    try:
        response = await model.acomplete(
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )

        content = response.content if hasattr(response, "content") else str(response)
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            return json.loads(json_match.group())
        else:
            return {
                "scores": {k: 5.0 for k in GDSCRIPT_QUALITY_CRITERIA},
                "feedback": f"Could not parse LLM response: {content[:200]}",
            }
    except Exception as e:
        return {
            "scores": {k: 5.0 for k in GDSCRIPT_QUALITY_CRITERIA},
            "feedback": f"LLM evaluation failed: {str(e)}",
        }


async def evaluate_code(
    code: str,
    scenario: EvalScenario,
    use_llm: bool = True,
    model_id: str = "gpt-4o",
) -> EvalResult:
    """Evaluate generated code against a scenario."""
    expected_found, forbidden_found, pattern_issues = check_patterns(
        code, scenario.expected_patterns, scenario.forbidden_patterns
    )

    pattern_score = (
        expected_found / len(scenario.expected_patterns) * 5
        - forbidden_found * 2
    )
    pattern_score = max(0, min(10, pattern_score))

    if use_llm:
        llm_result = await evaluate_with_llm(code, scenario, model_id)
        criteria_scores = llm_result.get("scores", {})
        feedback = llm_result.get("feedback", "")
    else:
        criteria_scores = {k: pattern_score for k in GDSCRIPT_QUALITY_CRITERIA}
        feedback = "; ".join(pattern_issues) if pattern_issues else "Pattern check passed"

    avg_score = sum(criteria_scores.values()) / len(criteria_scores) if criteria_scores else 0
    passed = avg_score >= 7.0 and forbidden_found == 0

    return EvalResult(
        scenario_name=scenario.name,
        score=avg_score,
        max_score=10.0,
        criteria_scores=criteria_scores,
        feedback=feedback,
        passed=passed,
    )


async def run_evaluation_suite(
    codes: dict[str, str],
    use_llm: bool = True,
    model_id: str = "gpt-4o",
) -> list[EvalResult]:
    """Run full evaluation suite on provided code samples."""
    results = []

    for scenario in EVAL_SCENARIOS:
        if scenario.name in codes:
            result = await evaluate_code(
                codes[scenario.name],
                scenario,
                use_llm=use_llm,
                model_id=model_id,
            )
            results.append(result)

    return results


def print_eval_report(results: list[EvalResult]) -> None:
    """Print formatted evaluation report."""
    print("\n" + "=" * 60)
    print("GDSCRIPT CODE QUALITY EVALUATION REPORT")
    print("=" * 60)

    total_score = 0
    total_max = 0

    for result in results:
        status = "[PASS]" if result.passed else "[FAIL]"
        print(f"\n{status} {result.scenario_name}")
        print(f"  Score: {result.score:.1f}/{result.max_score}")
        print(f"  Criteria:")
        for criterion, score in result.criteria_scores.items():
            print(f"    - {criterion}: {score:.1f}/10")
        print(f"  Feedback: {result.feedback[:100]}...")

        total_score += result.score
        total_max += result.max_score

    print("\n" + "-" * 60)
    overall = (total_score / total_max * 100) if total_max > 0 else 0
    passed = sum(1 for r in results if r.passed)
    print(f"Overall Score: {overall:.1f}%")
    print(f"Passed: {passed}/{len(results)} scenarios")
    print("=" * 60)


SAMPLE_PLAYER_CODE = '''
extends CharacterBody2D

@export var speed: float = 200.0
@export var jump_velocity: float = -400.0

var gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")


func _physics_process(delta: float) -> void:
    if not is_on_floor():
        velocity.y += gravity * delta

    if Input.is_action_just_pressed("jump") and is_on_floor():
        velocity.y = jump_velocity

    var direction := Input.get_axis("move_left", "move_right")
    if direction:
        velocity.x = direction * speed
    else:
        velocity.x = move_toward(velocity.x, 0, speed)

    move_and_slide()
'''


async def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate GDScript code quality")
    parser.add_argument("--model", default="gpt-4o", help="Model ID for LLM judge")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM evaluation")
    args = parser.parse_args()

    sample_codes = {
        "player_movement": SAMPLE_PLAYER_CODE,
    }

    results = await run_evaluation_suite(
        sample_codes,
        use_llm=not args.no_llm,
        model_id=args.model,
    )

    print_eval_report(results)


if __name__ == "__main__":
    asyncio.run(main())
