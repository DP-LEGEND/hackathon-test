"""Offline tests for coach.cue. A fake client stands in for Claude, so no API key or network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from coach.cue import MOCK_METRICS, CoachCue, CoachError, get_cue


class FakeClient:
    """Mimics client.beta.messages.parse and records what it was asked."""

    def __init__(self, parsed: CoachCue | None, stop_reason: str = "end_turn") -> None:
        self.calls: list[dict] = []
        response = SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason)
        messages = SimpleNamespace(parse=lambda **kwargs: (self.calls.append(kwargs), response)[1])
        self.beta = SimpleNamespace(messages=messages)


def test_returns_one_fix_and_cue_as_json() -> None:
    answer = CoachCue(
        metric="contact_point",
        fix="You hit the ball -18 cm behind your front foot. Meet it in front of you.",
        cue="Step in and hit the ball in front.",
    )
    client = FakeClient(answer)

    result = get_cue(MOCK_METRICS, client=client)  # type: ignore[arg-type]

    assert result == answer
    assert set(result.model_dump()) == {"metric", "fix", "cue"}
    sent = client.calls[0]["messages"][0]["content"]
    assert "contact_point_cm" in sent and "-18" in sent


def test_rejects_numbers_that_were_not_measured() -> None:
    answer = CoachCue(
        metric="shoulder_turn",
        fix="Turn your shoulders to 90 degrees.",  # 90 was never measured
        cue="Turn further before you swing.",
    )
    with pytest.raises(CoachError, match="not measured"):
        get_cue(MOCK_METRICS, client=FakeClient(answer))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "fix",
    [
        "Your elbow is at .148 of a turn.",  # leading decimal: 0.148, not 148
        "Your elbow is at 148.5 degrees.",  # 148 was measured, 148.5 was not
        "Your elbow is at 1.5e2 degrees.",  # scientific notation is read whole: 150, not 1.5 or 2
    ],
)
def test_rejects_numbers_that_only_look_measured(fix: str) -> None:
    answer = CoachCue(metric="elbow_bend", fix=fix, cue="Bend your elbow a little more.")
    with pytest.raises(CoachError, match="not measured"):
        get_cue(MOCK_METRICS, client=FakeClient(answer))  # type: ignore[arg-type]


def test_accepts_measured_number_at_sentence_end_and_as_a_size() -> None:
    answer = CoachCue(
        metric="contact_point",
        fix="Your elbow was 148. You met the ball 18 cm behind your front foot.",
        cue="Hit the ball in front of you.",
    )
    assert get_cue(MOCK_METRICS, client=FakeClient(answer)) == answer  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "cue, reason",
    [
        ("", "empty"),
        ("   ", "empty"),
        ("Step in. Hit it early.", "one sentence"),
        ("Step in with your front foot and then hit the ball well out in front.", "limit is 12"),
    ],
)
def test_rejects_cues_that_cannot_be_spoken_as_one_short_sentence(cue: str, reason: str) -> None:
    answer = CoachCue(metric="contact_point", fix="Meet the ball in front.", cue=cue)
    with pytest.raises(CoachError, match=reason):
        get_cue(MOCK_METRICS, client=FakeClient(answer))  # type: ignore[arg-type]


def test_refusal_raises_clear_error() -> None:
    with pytest.raises(CoachError, match="declined"):
        get_cue(MOCK_METRICS, client=FakeClient(None, stop_reason="refusal"))  # type: ignore[arg-type]


def test_metric_must_be_one_of_the_four() -> None:
    with pytest.raises(ValueError):
        CoachCue(metric="hip_turn", fix="x", cue="y")  # type: ignore[arg-type]


# ---- Contact point is optional (the pipeline doesn't measure it yet) ------------------

NO_CONTACT = MOCK_METRICS.model_copy(update={"contact_point_cm": None})


def test_metrics_work_without_contact_point() -> None:
    from coach.cue import SwingMetrics

    m = SwingMetrics(elbow_bend_deg=148, shoulder_turn_deg=62, wrist_angle_deg=131)
    assert m.contact_point_cm is None
    assert "contact_point_cm" not in m.measured()


def test_missing_contact_point_is_left_out_of_the_prompt() -> None:
    answer = CoachCue(metric="shoulder_turn", fix="Your shoulders turned 62 degrees.",
                      cue="Turn your shoulders further before you swing.")
    client = FakeClient(answer)
    assert get_cue(NO_CONTACT, client=client) == answer  # type: ignore[arg-type]
    sent = client.calls[0]["messages"][0]["content"]
    assert "contact_point" not in sent and "62" in sent


def test_rejects_picking_an_unmeasured_metric() -> None:
    answer = CoachCue(metric="contact_point", fix="Meet the ball in front.",
                      cue="Hit the ball in front of you.")
    with pytest.raises(CoachError, match="wasn't measured"):
        get_cue(NO_CONTACT, client=FakeClient(answer))  # type: ignore[arg-type]


def test_missing_contact_point_number_cannot_be_quoted() -> None:
    answer = CoachCue(metric="elbow_bend", fix="Contact was -18 cm and your elbow 148.",
                      cue="Bend your elbow a little more.")
    with pytest.raises(CoachError, match="not measured"):
        get_cue(NO_CONTACT, client=FakeClient(answer))  # type: ignore[arg-type]
