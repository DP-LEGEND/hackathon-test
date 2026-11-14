"""HTTP contracts using the checked-in sample; no provider calls or real clips."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coach.agent import coach_swing
from physics.compare import compare
from physics.ghost import FIXES
from pipeline.server import app


@pytest.fixture
def api(tmp_path, monkeypatch):
    session = tmp_path / 'sample-run'
    session.mkdir()
    sample = json.loads((Path(__file__).resolve().parents[3] /
                         'data/samples/swing_sample.json').read_text())
    sample.update(id='sample', fps=30, fpsReal=120, contactFrame=12, side='backhand')
    # Inject an audio-timed contact to prove it survives every API measurement.
    # The checked-in sample's original contact itself is only an estimate.
    sample['metadata'] = {'contactMethod': 'audio-transient'}
    (session / 'sample.json').write_text(json.dumps(sample))
    (session / 'manifest.json').write_text(json.dumps({'files': ['sample.json']}))
    labels = tmp_path / 'labels.csv'
    monkeypatch.setenv('GHOST_SWINGS_DIR', str(tmp_path))
    monkeypatch.setenv('GHOST_LABELS_CSV', str(labels))
    return TestClient(app), sample, session, labels


def test_coach_measures_stored_contact_and_returns_usable_fix(api):
    client, sample, _, _ = api
    expected = coach_swing(sample, stroke='backhand', fps_real=120)
    response = client.post('/coach/sample')
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['fault'] == expected['fault']
    assert result['cue'] == expected['cue']
    assert result['metrics'] == expected['metrics']
    assert result['metrics']['contact_frame'] == result['contactFrame'] == 12
    assert result['contactMethod'] == 'audio-transient'
    assert result['fix'] in FIXES and result['amount'] == expected['fix_amount']
    assert result['ghost_ready'] is True


def test_compare_returns_both_skeletons_metrics_and_court_paths(api):
    client, sample, _, _ = api
    request = {'fix': 'bend_elbow', 'amount': 12}
    result = client.post('/compare/sample', json=request)
    assert result.status_code == 200, result.text
    result = result.json()
    assert result == compare(sample, 'bend_elbow', 12, fps_real=120)
    assert result['contactFrame'] == 12 and result['fpsReal'] == 120
    for side in ('you', 'ghost'):
        assert result[side]['swing']['contactFrame'] == 12
        assert len(result[side]['swing']['frames']) == len(sample['frames'])
        assert result[side]['metrics']
        ball = result[side]['ball']
        assert ball['predicted'] is True and ball['label'] == 'PREDICTED'
        assert all(len(point) == 3 for point in ball['points'])
        assert ball['points'][0] == result['assumptions']['contactSpot']
    assert result['delta']['metrics']
    assert client.post('/swings/sample/ghost', json=request).json() == result


@pytest.mark.parametrize('fault,label', [('none', 'good'), ('good', 'good'),
    ('early_wrist', 'early_wrist'), ('over_rotation', 'over_rotation'),
    ('straight_arm', 'straight_arm'), ('open_stance', 'open_stance'),
    ('rolled_wrist', 'rolled_wrist'), ('unlabelled', None)])
def test_labels_csv_schema(api, fault, label):
    client, _, _, labels = api
    labels.write_text(f'clip,swing,side,intended_fault,pipeline_run\nIMG_2116,sample,backhand,{fault},sample-run\n')
    assert client.get('/swings').json() == {'swings': [{'id': 'sample', 'label': label}]}


def test_session_specific_label_wins_and_missing_labels_are_null(api):
    client, _, _, labels = api
    assert client.get('/swings').json()['swings'][0]['label'] is None
    labels.write_text('swing,intended_fault\nsample,none\nsample@sample-run,straight_arm\n')
    assert client.get('/swings').json()['swings'][0]['label'] == 'straight_arm'


def test_label_file_errors_are_explicit(api):
    client, _, _, labels = api
    for text in ('wrong,columns\n', 'swing,intended_fault\nsample,none\nsample,open_stance\n'):
        labels.write_text(text)
        assert client.get('/swings').status_code == 503


@pytest.mark.parametrize('contact', [None, -1, 99999, True, 1.5])
def test_invalid_contact_never_silently_uses_speed_peak(api, contact):
    client, sample, session, _ = api
    sample['contactFrame'] = contact
    (session / 'sample.json').write_text(json.dumps(sample))
    assert client.post('/coach/sample').status_code == 422
    assert client.post('/compare/sample', json={'fix': 'bend_elbow', 'amount': 12}).status_code == 422


def test_unknown_swing_and_invalid_compare(api):
    client, _, _, _ = api
    assert client.post('/coach/unknown').status_code == 404
    assert client.post('/compare/unknown', json={'fix': 'bend_elbow', 'amount': 12}).status_code == 404
    for body in ({'fix': 'missing', 'amount': 1}, {'fix': 'bend_elbow', 'amount': 'NaN'}, {}):
        assert client.post('/compare/sample', json=body).status_code == 422


def test_no_fault_or_unavailable_fix_has_no_actionable_ghost(api, monkeypatch):
    import pipeline.server as server
    client, _, _, _ = api
    for fault, fix in ((None, None), ({'id': 'rolling_wrist'}, 'firm_wrist')):
        monkeypatch.setattr(server, 'coach_swing', lambda *args, **kwargs: {
            'fault': fault, 'cue': 'Keep going.', 'fix': fix, 'fix_amount': 12,
            'ghost_ready': False, 'metrics': {}})
        response = client.post('/coach/sample').json()
        assert response['fault'] == fault and response['fix'] is None
        assert response['amount'] is None and response['ghost_ready'] is False

def test_repeated_pipeline_runs_have_addressable_labelled_ids(api):
    client, sample, session, labels = api
    second = session.parent / 'rerun'
    second.mkdir()
    (second / 'manifest.json').write_text(json.dumps({'files': ['sample.json']}))
    (second / 'sample.json').write_text(json.dumps(sample))
    labels.write_text('swing,intended_fault\nsample@sample-run,none\nsample@rerun,early_wrist\n')
    entries = client.get('/swings').json()['swings']
    assert {row['id']: row['label'] for row in entries} == {
        'sample@sample-run': 'good', 'sample@rerun': 'early_wrist'}
    for entry in entries:
        assert client.get(f"/swings/{entry['id']}").json()['id'] == entry['id']
        assert client.post(f"/coach/{entry['id']}").status_code == 200

def test_original_sample_preserves_its_estimated_contact(api):
    client, _, session, _ = api
    original = json.loads((Path(__file__).resolve().parents[3] /
                           'data/samples/swing_sample.json').read_text())
    original['id'] = 'sample'
    (session / 'sample.json').write_text(json.dumps(original))
    result = client.post('/coach/sample')
    assert result.status_code == 200
    assert result.json()['contactFrame'] == original['contactFrame']
    assert result.json()['contactMethod'] == 'provided-contact-estimate'
    compared = client.post('/compare/sample', json={'fix': 'bend_elbow', 'amount': 10})
    assert compared.status_code == 200
    assert compared.json()['contactFrame'] == original['contactFrame']
