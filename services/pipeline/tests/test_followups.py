"""Synthetic regressions, not real-clip validation."""
import json
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pipeline.process import Options, swings_from_raw
from pipeline.segment import find_swings
from pipeline.server import app
from pipeline.timing import Timeline
from pipeline.tests.test_stereo_cli import stereo_pair
from pipeline.tests.test_swing_detection import motion_clip

@pytest.mark.parametrize('before,after', [(0,1476),(80,1310)])
def test_switches(before,after):
    clock=Timeline(4,before,after)
    end=before+(after-before)/4
    np.testing.assert_allclose(clock.real([after-4,after,after+1]),[end-1,end,end+1])
    np.testing.assert_allclose(clock.factor([0,before,after]),[1 if before else 4,4,1])

@pytest.mark.parametrize('kwargs',[{'realtime_before':-1},{'realtime_after':float('nan')},{'realtime_before':80,'realtime_after':40}])
def test_invalid_switches(kwargs):
    with pytest.raises(ValueError): Timeline(4,**kwargs)

def test_fallback():
    raw=motion_clip(kind='feed')
    assert find_swings(raw)==[]
    found=find_swings(raw,speed_fallback=True)
    assert len(found)==1 and found[0]['detection']=='speed_peak'
    assert find_swings(raw,speed_fallback=True,min_speed=100)==[]

@pytest.mark.parametrize('slowdown',[1,4])
def test_audio_half_second(slowdown):
    raw=motion_clip(fps=120,slowdown=slowdown)
    settings=dict(slowdown=slowdown,min_speed=7,min_gap_real_s=2.5,confirm_s=.5,require_audio=True,speed_fallback=True)
    assert find_swings(raw,hits=np.array([]),**settings)==[]
    assert len(find_swings(raw,hits=np.array([1.25*slowdown]),**settings))==1
    assert find_swings(raw,hits=np.array([1.4*slowdown]),**settings)==[]

def test_tap_spacing():
    found=find_swings(motion_clip(contacts=(.6,1.5)),hits=np.array([.6,1.5]),require_audio=True,confirm_s=.5,min_gap_real_s=2.5,min_speed=7)
    assert len(found)==1
    assert find_swings(motion_clip(kind='walk'),min_speed=7,speed_fallback=True)==[]

def test_fallback_metadata_and_gate(stereo_pair):
    a,b,*_=stereo_pair
    a['img'][:,16,0]=700+200*(1+np.tanh((a['t']-.8)/.035))/2
    swings,_=swings_from_raw(a,b)
    assert swings and swings[0]['metadata']['detection']=='speed_peak'
    a['vis'][60:150,13]=0
    _,report=swings_from_raw(a,b)
    assert '13' in report['rejected'][0]['reason']
    assert report['rejected'][0]['sourcePeakSeconds']==pytest.approx(.8,abs=.05)

def test_pipeline_switches(stereo_pair,monkeypatch):
    import pipeline.process as process
    a,b,*_=stereo_pair
    a['t']=np.arange(len(a['t']))/30
    a['fps']=30
    b['t']=Timeline(4,1,5).real(a['t'])
    def detection(raw,**kwargs):
        n=len(raw['t'])
        return [{'start':2,'end':n-3,'peak':n//2,'speed':10,'detection':'speed_peak'}]
    monkeypatch.setattr(process,'find_swings',detection)
    swings,report=swings_from_raw(a,b,Options(slowdown_a=4,a_realtime_before=1,a_realtime_after=5))
    assert report['written']==3
    assert [s['fpsReal'] for s in swings]==[30,120,30]
    assert [s['metadata']['realtime'] for s in swings]==[True,False,True]
    for swing in swings:
        np.testing.assert_allclose(np.diff([f['t'] for f in swing['frames']]),1/swing['fps'])

@pytest.fixture
def api(tmp_path,monkeypatch):
    monkeypatch.setenv('GHOST_SWINGS_DIR',str(tmp_path))
    session=tmp_path/'session';session.mkdir()
    sample=json.loads((Path(__file__).resolve().parents[3]/'data/samples/swing_sample.json').read_text())
    sample['id']='test-swing'
    (session/'test-swing.json').write_text(json.dumps(sample))
    (session/'manifest.json').write_text(json.dumps({'files':['test-swing.json']}))
    return TestClient(app),session

def test_api(api):
    client,_=api
    assert client.get('/swings').json()=={'swings':[{'id':'test-swing','label':None}]}
    assert client.get('/swings/test-swing').json()['id']=='test-swing'
    response=client.post('/swings/test-swing/ghost',json={'fix':'straighten_elbow','amount':12})
    assert response.status_code==200,response.text
    assert response.json()['you']['ball']['label']=='PREDICTED'
    assert client.get('/swings/missing').status_code==404
    for body in ({'fix':'invalid','amount':1},{'fix':'straighten_elbow','amount':'NaN'},{'fix':'straighten_elbow'},{'fix':'straighten_elbow','amount':1001}):
        assert client.post('/swings/test-swing/ghost',json=body).status_code==422

def test_api_bad_manifest(api):
    client,session=api
    for content in ('not json',json.dumps({'files':['../../private.json']})):
        (session/'manifest.json').write_text(content)
        response=client.get('/swings')
        assert response.status_code==503 and 'private' not in response.text

def test_occluded_windup_edge_is_cropped_not_fabricated(stereo_pair, monkeypatch):
    import pipeline.process as process
    a, b, *_ = stereo_pair
    monkeypatch.setattr(process, 'find_swings', lambda *args, **kwargs: [
        {'start': 0, 'end': 110, 'peak': 72, 'speed': 10, 'detection': 'speed_peak'}])
    a['vis'][:35, 13] = 0  # unbounded gap cannot be interpolated
    swings, report = swings_from_raw(a, b)
    assert report['written'] == 1
    assert swings[0]['metadata']['croppedForCoreVisibility']
    assert swings[0]['metadata']['sourceStartFrame'] == 35
    assert swings[0]['metadata']['sourceContactFrame'] == 72


def test_stereo_sampling_uses_piecewise_real_time():
    from pipeline.stereo import sample_b_at_a
    clock = Timeline(4, 80, 1310)
    playback = np.array([0., 80., 84., 1310., 1311.])
    real = clock.real(playback)
    b = {'t': real, 'img': np.broadcast_to(real[:, None, None], (5, 33, 3)),
         'vis': np.ones((5, 33))}
    image, vis = sample_b_at_a({'t': real}, b, 1, 0)
    np.testing.assert_allclose(image[:, 16, 0], real)
    assert vis.min() == 1


def test_audio_contact_is_used_by_pipeline(stereo_pair, monkeypatch):
    import pipeline.process as process
    a, b, *_ = stereo_pair
    monkeypatch.setattr(process, 'audio_hits', lambda *args, **kwargs: np.array([.65]))
    swings, _ = swings_from_raw(a, b, Options(hits_wav='injected.wav'))
    assert len(swings) == 2
    assert swings[1]['metadata']['contactMethod'] == 'wrist-speed-peak-estimate'
    swing = swings[0]
    assert swing['metadata']['contactMethod'] == 'audio-transient'
    assert a['t'][swing['metadata']['sourceContactFrame']] == pytest.approx(.65)


def test_api_cors_and_missing_catalogue(api, monkeypatch, tmp_path):
    client, _ = api
    response = client.options('/swings/test-swing/ghost', headers={
        'Origin': 'http://localhost:3000', 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'})
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://localhost:3000'
    monkeypatch.setenv('GHOST_SWINGS_DIR', str(tmp_path / 'missing'))
    assert client.get('/swings').json() == {'swings': []}

def test_audio_wav_validation_and_transient_detection(tmp_path):
    import wave
    from pipeline.segment import audio_hits
    path = tmp_path / 'hits.wav'
    rng = np.random.default_rng(7)
    samples = np.zeros(32000, dtype=np.int16)
    samples[16000:16320] = rng.integers(-25000, 25000, 320, dtype=np.int16)
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(samples.tobytes())
    found = audio_hits(str(path), rise_db=25)
    assert len(found) == 1 and found[0] == pytest.approx(1, abs=.05)
    path.write_bytes(b'not a WAV')
    with pytest.raises(ValueError, match='Invalid hits WAV'):
        audio_hits(str(path))


def test_unconfirmed_stronger_peak_does_not_suppress_audio_hit():
    raw = motion_clip(contacts=(.6, 1.8))
    raw['img'][:, 16, 0] += 250 * (1 + np.tanh((raw['t'] - .6) / .02)) / 2
    found = find_swings(raw, hits=np.array([1.8]), require_audio=True,
                        speed_fallback=True, min_speed=7, min_gap_real_s=2.5, confirm_s=.5)
    assert len(found) == 1
    assert raw['t'][found[0]['peak']] == pytest.approx(1.8, abs=.05)
