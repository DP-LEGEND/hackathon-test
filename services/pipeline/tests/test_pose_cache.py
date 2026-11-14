"""Pose-cache tests inject extraction; no model/video/network needed."""
import numpy as np
import pytest

from pipeline.cache import extract_pair


@pytest.fixture
def cached_pair(tmp_path):
    paths = [tmp_path / name for name in ('a.mov', 'b.mov', 'pose.task')]
    for path in paths:
        path.write_bytes(path.name.encode())
    calls = []
    def extract(clip, **kwargs):
        calls.append(clip)
        return {'fps': 30., 'size': (1280, 720), 't': np.arange(3) / 30,
                'img': np.ones((3, 33, 3)), 'world': np.ones((3, 33, 3)),
                'vis': np.ones((3, 33))}
    return paths, extract, calls


def test_cache_reuses_both_streams_and_refreshes_on_request(tmp_path, cached_pair):
    paths, extract, calls = cached_pair
    out = tmp_path / 'cache'
    first = extract_pair(*map(str, paths), out, extract)
    second = extract_pair(*map(str, paths), out, extract)
    assert len(calls) == 2
    for old, new in zip(first, second):
        for key in old:
            np.testing.assert_array_equal(old[key], new[key])
    extract_pair(*map(str, paths), out, extract, no_cache=True)
    assert len(calls) == 4
    assert list(out.glob('.raw-cache-*')) == []


@pytest.mark.parametrize('changed', [0, 1, 2])
def test_cache_invalidates_changed_clip_or_model_bytes(tmp_path, cached_pair, changed):
    paths, extract, calls = cached_pair
    out = tmp_path / 'cache'
    extract_pair(*map(str, paths), out, extract)
    original = paths[changed].read_bytes()
    paths[changed].write_bytes(bytes(x ^ 1 for x in original))  # same length/path
    extract_pair(*map(str, paths), out, extract)
    assert len(calls) == 4


def test_corrupt_cache_is_recomputed_without_pickle(tmp_path, cached_pair):
    paths, extract, calls = cached_pair
    out = tmp_path / 'cache'
    extract_pair(*map(str, paths), out, extract)
    (out / 'raw_cache.npz').write_bytes(b'not an npz')
    extract_pair(*map(str, paths), out, extract)
    assert len(calls) == 4


def test_camera_assignment_is_part_of_cache_identity(tmp_path, cached_pair):
    paths, extract, calls = cached_pair
    out = tmp_path / 'cache'
    extract_pair(*map(str, paths), out, extract)
    extract_pair(str(paths[1]), str(paths[0]), str(paths[2]), out, extract)
    assert len(calls) == 4


def test_failed_cache_refresh_preserves_previous_cache(tmp_path, cached_pair, monkeypatch):
    paths, extract, calls = cached_pair
    out = tmp_path / 'cache'
    extract_pair(*map(str, paths), out, extract)
    saved = (out / 'raw_cache.npz').read_bytes()
    def fail(*args, **kwargs):
        raise OSError('simulated disk write failure')
    monkeypatch.setattr(np, 'savez_compressed', fail)
    with pytest.raises(OSError, match='simulated disk write failure'):
        extract_pair(*map(str, paths), out, extract, no_cache=True)
    assert (out / 'raw_cache.npz').read_bytes() == saved
    assert list(out.glob('.raw-cache-*')) == []
