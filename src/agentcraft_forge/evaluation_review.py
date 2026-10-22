"""Revisión humana vinculada al informe exacto; nunca ejecuta el proyecto."""

import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from agentcraft_forge.evaluation import (
    Strict,
    Suite,
    assess,
    read_json_document,
    read_json_file,
)


class ReviewItem(Strict):
    case_id: str
    repetition: int = Field(ge=1, le=10, strict=True)
    criteria: list[str]
    answers: list[Annotated[bool, Field(strict=True)] | None]
    notes: str = Field(default="", max_length=2000)


class ReviewDocument(Strict):
    schema_version: Literal[1] = 1
    report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer: Annotated[str, Field(min_length=2, max_length=100)] | None = None
    reviews: list[ReviewItem] = Field(max_length=1000)


def prepare_review(report_path: Path) -> tuple[dict, ReviewDocument]:
    report, content = read_json_document(report_path)
    if report.get("mode") not in {"offline", "live"} or "metrics" not in report:
        raise ValueError("Solo se revisan informes ejecutados.")
    suite = Suite.model_validate(report["suite"])
    cases = {case.id: case for case in suite.cases}
    seen = set()
    items = []
    for trial in report["trials"]:
        key = (trial["case_id"], trial["repetition"])
        if (
            key in seen
            or key[0] not in cases
            or type(key[1]) is not int
            or not 1 <= key[1] <= suite.repetitions
        ):
            raise ValueError("Intento duplicado o ajeno a la suite.")
        seen.add(key)
        case = cases[key[0]]
        if trial["human_review"] != case.human_review:
            raise ValueError("La revisión del intento no coincide con su caso.")
        if case.human_review:
            items.append(
                ReviewItem(
                    case_id=case.id,
                    repetition=key[1],
                    criteria=case.review_criteria,
                    answers=[None] * len(case.review_criteria),
                )
            )
    template = ReviewDocument(
        report_sha256=hashlib.sha256(content).hexdigest(),
        reviews=items,
    )
    return report, template


def apply_review(report_path: Path, reviews_path: Path) -> dict:
    report, template = prepare_review(report_path)
    document = ReviewDocument.model_validate(read_json_file(reviews_path))
    if document.report_sha256 != template.report_sha256:
        raise ValueError("La revisión corresponde a otro informe o el informe cambió.")
    expected = {(item.case_id, item.repetition): item for item in template.reviews}
    approvals = {}
    seen = set()
    for item in document.reviews:
        key = (item.case_id, item.repetition)
        if key in seen or key not in expected:
            raise ValueError("Revisión duplicada o intento desconocido.")
        seen.add(key)
        if item.criteria != expected[key].criteria or len(item.answers) != len(
            item.criteria
        ):
            raise ValueError("Los criterios de revisión no coinciden con el informe.")
        if any(answer is not None for answer in item.answers):
            if (
                not document.reviewer
                or not document.reviewer.strip()
                or not item.notes.strip()
            ):
                raise ValueError(
                    "Identifique a quien revisa y añada una nota con evidencia."
                )
        if any(answer is False for answer in item.answers):
            approvals[key] = False
        elif all(answer is True for answer in item.answers):
            approvals[key] = True
    return {
        "schema_version": 1,
        "report_sha256": template.report_sha256,
        "reviewer": document.reviewer,
        "quality_gate": assess(report, approvals),
        "reviews": document.model_dump(mode="json")["reviews"],
        "limitations": "Anotación humana declarada; no es una firma ni verifica la identidad de quien revisa.",
    }
