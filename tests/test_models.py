import numpy as np
import pytest

from dsp2si.models import errors, normalize_a, normalize_b, stimulus, OUT_MAX, OUT_MIN


def octave_grid():
    """Every octave of magnitude from 1 LSB to full scale, 2048 angles each."""
    mag = 2.0 ** np.arange(0, 15.01, 0.25)
    ang = np.linspace(-np.pi, np.pi, 2048, endpoint=False)
    m, a = np.meshgrid(mag, ang)
    i = np.clip(np.round(m * np.cos(a)), OUT_MIN, OUT_MAX).astype(np.int64).ravel()
    q = np.clip(np.round(m * np.sin(a)), OUT_MIN, OUT_MAX).astype(np.int64).ravel()
    return i, q


@pytest.mark.parametrize("model", [normalize_a, normalize_b])
@pytest.mark.parametrize("inputs", [stimulus, octave_grid])
def test_within_one_lsb(model, inputs):
    i, q = inputs()
    x, y = model(i, q)
    e = errors(x, y, i, q)
    assert e["max_lsb"] < 1.0, e


@pytest.mark.parametrize("model", [normalize_a, normalize_b])
def test_zero_and_range(model):
    x, y = model(np.array([0]), np.array([0]))
    assert x[0] == 0 and y[0] == 0
    i, q = stimulus(20_000, seed=7)
    x, y = model(i, q)
    assert x.min() >= OUT_MIN and x.max() <= OUT_MAX and y.min() >= OUT_MIN and y.max() <= OUT_MAX
