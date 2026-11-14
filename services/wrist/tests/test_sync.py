"""Taps, impacts and video alignment (MOCK data from wrist.synth)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wrist.impact import G
from wrist.sync import (
    MIN_IMPACT_G, MIN_SWING_DPS, TAP_ONLY_CLEAR_MS, Spike, SyncError, align, find_impacts, read_contacts, synchronise,
)


def test_finds_both_taps(session) -> None:
    taps = session.sync["taps_s"]
    assert taps is not None
    for got, want in zip(taps, session.truth["taps_s"]):
        assert got == pytest.approx(want, abs=0.015)


def test_finds_every_impact_and_rejects_the_footstep(session) -> None:
    a = session.sync["alignment"]
    assert a["n_impacts"] == len(session.truth["swings"]) and not a["count_mismatch"]
    for pair in a["pairs"]:
        assert pair["impact_s"] == pytest.approx(session.truth["swings"][pair["swing"]]["impact_s"], abs=0.015)
    rejected = session.sync["rejected_spikes"]
    assert any(abs(r["t"] - session.truth["footstep_s"]) < 0.02 and "arm still" in r["why"] for r in rejected)


def test_first_tap_alignment_reports_small_errors(session) -> None:
    a = session.sync["alignment"]
    assert a["offset_from"] == "first tap"
    assert a["offset_s"] == pytest.approx(session.truth["video_offset_s"], abs=0.02)
    assert a["error_ms"]["n_ok"] == a["error_ms"]["n_pairs"] == 10
    assert a["error_ms"]["mean_abs"] < 20 and a["error_ms"]["max_abs"] < 40
    assert set(session.sync["impacts"]) == set(session.truth["swings"])
    assert session.sync["warnings"] == [] and session.sync["tap_only"] == {}


def test_without_video_tap_the_offset_is_fitted_and_flagged(session) -> None:
    s = synchronise(session.rec, session.contacts)
    assert s["alignment"]["offset_from"].startswith("fitted")
    assert any("--video-tap" in w for w in s["warnings"])
    assert s["alignment"]["error_ms"]["n_ok"] == 10


def test_a_missing_video_contact_only_spoils_its_own_pair(session) -> None:
    contacts = session.contacts[:3] + session.contacts[4:]  # the video lost swing 4
    s = synchronise(session.rec, contacts, video_tap_s=session.truth["video_tap_s"])
    a = s["alignment"]
    assert a["count_mismatch"] and a["n_impacts"] == 10 and a["n_contacts"] == 9
    assert a["error_ms"]["n_ok"] == 9, "every remaining swing still pairs with its own impact"
    missing = session.truth["swings"][session.contacts[3][0]]["impact_s"]
    assert a["unpaired_impacts_s"] == [pytest.approx(missing, abs=0.015)]
    assert any("nearest impact in order" in w for w in s["warnings"])


def test_a_contact_with_no_impact_is_not_trusted_and_spoils_nothing_else(session) -> None:
    mid = (session.contacts[4][1] + session.contacts[5][1]) / 2  # a swing the sensor never felt
    extra = session.contacts + [("ghost-mid", mid), ("ghost-end", session.contacts[-1][1] + 5.0)]
    s = synchronise(session.rec, extra, video_tap_s=session.truth["video_tap_s"])
    pairs = {p["swing"]: p for p in s["alignment"]["pairs"]}
    assert pairs["ghost-mid"]["ok"] is False and abs(pairs["ghost-mid"]["error_ms"]) > 1000
    assert s["alignment"]["unpaired_swings"] == ["ghost-end"]
    assert set(s["impacts"]) == set(session.truth["swings"]), "all 10 real swings still pair"


def test_wrong_time_scale_shows_up_as_alignment_errors(session) -> None:
    s = synchronise(session.rec, session.contacts, video_tap_s=session.truth["video_tap_s"], video_scale=1.05)
    assert s["alignment"]["error_ms"]["n_ok"] < 10
    assert any("off by more than" in w for w in s["warnings"])


def test_impacts_need_a_moving_forearm_a_real_knock_and_one_per_swing() -> None:
    spikes = [Spike(5.0, 50, 10), Spike(10.0, 80, 900), Spike(10.3, 120, 1100), Spike(20.0, 90, 1000),
              Spike(30.0, 11, 1300)]  # a fast swing's own pull: ~1 g after the high-pass, no ball
    impacts, rejected = find_impacts(spikes, after_t=1.0)
    assert [s.t for s in impacts] == [10.3, 20.0], "the biggest spike of a swing wins"
    assert [r["t"] for r in rejected] == [5.0, 30.0]
    assert str(int(MIN_SWING_DPS)) in rejected[0]["why"]
    assert "too small" in rejected[1]["why"] and f"{MIN_IMPACT_G:g} g" in rejected[1]["why"]
    assert find_impacts([Spike(30.0, MIN_IMPACT_G * G + 0.1, 1300)], after_t=1.0)[0], "just over the floor counts"


def test_a_shadow_swing_is_timed_from_the_double_tap(shadow) -> None:
    a = shadow.sync["alignment"]
    assert [t["swing"] for t in a["tap_only"]] == ["synth-05"] and not a["count_mismatch"]
    true_contact = shadow.truth["swings"]["synth-05"]["impact_s"]  # when the ball would have been hit
    assert a["tap_only"][0]["contact_s"] == pytest.approx(true_contact, abs=0.04), "within the sync error"
    assert shadow.sync["tap_only"] == {"synth-05": a["tap_only"][0]["contact_s"]}
    assert set(shadow.sync["impacts"]) == set(shadow.truth["swings"]) - {"synth-05"}, "the other 9 pair as before"
    assert a["error_ms"]["n_ok"] == a["error_ms"]["n_pairs"] == 9
    assert any("synth-05" in w and "double tap" in w for w in shadow.sync["warnings"])
    assert any(abs(r["t"] - true_contact) < 0.03 and "too small" in r["why"] for r in shadow.sync["rejected_spikes"])


def test_without_the_video_tap_a_shadow_swing_is_not_timed(shadow) -> None:
    s = synchronise(shadow.rec, shadow.contacts)
    assert s["alignment"]["tap_only"] == [] and s["tap_only"] == {}
    assert s["alignment"]["count_mismatch"] and s["alignment"]["error_ms"]["n_ok"] < 10


def test_tap_only_needs_no_impact_nearby_and_a_swinging_arm() -> None:
    contacts = [("near", 8.2), ("shadow", 13.0), ("still", 16.0), ("hit", 18.0)]   # offset 2.0 from the tap
    a = align([10.0, 20.0], contacts, tap_s=2.0, video_tap_s=0.0, swinging=lambda t: t != 18.0)
    pairs = {p["swing"]: p for p in a["pairs"]}
    assert a["tap_only"] == [{"swing": "shadow", "contact_s": 15.0, "contact_video_s": 13.0}]
    assert pairs["still"]["ok"] is False, "no impact near, but the arm isn't swinging: untrusted, as before"
    assert pairs["near"]["ok"] is False and pairs["near"]["error_ms"] == pytest.approx(-200)
    assert 100 < abs(pairs["near"]["error_ms"]) < TAP_ONLY_CLEAR_MS, "an impact 200 ms off is a sync failure"
    assert pairs["hit"]["ok"] is True
    b = align([10.0, 20.0], contacts, tap_s=2.0, video_tap_s=0.0, swinging=lambda t: False)
    assert b["tap_only"] == [], "an arm that isn't swinging is never a shadow swing"
    assert align([10.0, 20.0], contacts, tap_s=2.0, video_tap_s=0.0)["tap_only"] == [], "no swinging check, no tap-only"


def test_align_by_index_without_tap() -> None:
    a = align([10.0, 20.0, 30.0], [("a", 8.0), ("b", 18.02), ("c", 27.98)])
    assert a["offset_s"] == pytest.approx(2.0)
    assert [p["error_ms"] for p in a["pairs"]] == pytest.approx([0.0, -20.0, 20.0])
    with pytest.raises(SyncError):
        align([], [("a", 1.0)])


def test_read_contacts_from_labels_csv_and_swing_folder(tmp_path: Path) -> None:
    labels = tmp_path / "labels.csv"
    labels.write_text("clip,swing,side,intended_fault,pipeline_run,contact_playback_s\n"
                      "C,s-02@bh-05,backhand,rolled_wrist,bh-05,40.5\n"
                      "C,s-01@bh-05,backhand,none,bh-05,12.25\n"
                      "C,s-09,backhand,none,bh-04,99.0\n"
                      "C,s-03@bh-05,backhand,none,bh-05,\n")
    assert read_contacts(labels, run="bh-05") == [("s-01", 12.25), ("s-02", 40.5)]
    assert len(read_contacts(labels)) == 3

    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "a.json").write_text(json.dumps({"id": "sw-a", "frames": [], "metadata": {"sourceContactSeconds": 7.5}}))
    (folder / "b.json").write_text(json.dumps({"id": "sw-b", "frames": [], "metadata": {"sourceContactSeconds": 3.0}}))
    (folder / "manifest.json").write_text(json.dumps({"files": ["a.json"]}))
    assert read_contacts(folder) == [("sw-b", 3.0), ("sw-a", 7.5)]

    with pytest.raises(SyncError, match="contact"):
        bad = tmp_path / "bad.csv"
        bad.write_text("swing,when\nx,1\n")
        read_contacts(bad)
