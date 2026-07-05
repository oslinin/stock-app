from app.indicators.macd import ema, macd, last_defined


def test_ema_seed_and_recursion():
    out = ema([1, 2, 3, 4, 5], 3)
    assert out[0] is None and out[1] is None
    assert out[2] == 2.0  # SMA seed
    assert out[3] == 3.0  # 4*0.5 + 2*0.5
    assert out[4] == 4.0


def test_macd_alignment():
    closes = [float(i) for i in range(60)]
    out = macd(closes, fast=12, slow=26, signal=9)
    line, sig = out["line"], out["signal"]
    assert line[24] is None and line[25] is not None
    first_sig = next(i for i, v in enumerate(sig) if v is not None)
    assert first_sig == 25 + 8


def test_macd_constant_series_is_zero():
    out = macd([20.0] * 60)
    assert abs(out["line"][-1]) < 1e-9
    assert abs(out["hist"][-1]) < 1e-9


def test_macd_rising_series_positive():
    closes = [10 + 0.5 * i for i in range(60)]
    out = macd(closes)
    assert out["line"][-1] > 0


def test_last_defined():
    assert last_defined([None, 1.0, 2.0, 3.0], 2) == [2.0, 3.0]
    assert last_defined([None, 1.0], 3) is None
