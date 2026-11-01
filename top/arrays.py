"""Small array helpers for hosts that cannot load a modern NumPy wheel."""

from __future__ import annotations

import math

_bsum = sum
_bmax = max
_bmin = min
_babs = abs
_bany = any

nan = float("nan")
pi = math.pi
NAN = nan


def _is_nan(value):
    return isinstance(value, float) and math.isnan(value)


def _num(value):
    if isinstance(value, Array):
        if len(value) != 1:
            raise TypeError("expected a scalar array")
        return value.data[0]
    return float(value)


class Array:
    def __init__(self, data, bool_=False):
        if bool_:
            self.data = [bool(item) for item in data]
            self.is_bool = True
        else:
            converted = []
            for item in data:
                if item is None or _is_nan(item):
                    converted.append(NAN)
                else:
                    converted.append(float(item))
            self.data = converted
            self.is_bool = False

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def __repr__(self):
        return f"Array({self.data[:8]}{'...' if len(self.data) > 8 else ''})"

    def copy(self):
        return Array(self.data, bool_=self.is_bool)

    def tolist(self):
        return list(self.data)

    def astype(self, kind):
        if self.is_bool:
            return Array((1.0 if item else 0.0 for item in self.data))
        return self.copy()

    def mean(self):
        return mean(self)

    def sum(self):
        return sum_(self)

    def min(self):
        return min_(self)

    def max(self):
        return max_(self)

    def any(self):
        return _bany(item for item in self.data)

    def __getitem__(self, key):
        if isinstance(key, Array) and key.is_bool:
            picked = [self.data[i] for i, flag in enumerate(key.data) if flag]
            return Array(picked, bool_=self.is_bool)
        if isinstance(key, slice):
            return Array(self.data[key], bool_=self.is_bool)
        value = self.data[key]
        return bool(value) if self.is_bool else value

    def __setitem__(self, key, value):
        if isinstance(key, Array) and key.is_bool:
            incoming = value.data if isinstance(value, Array) else None
            cursor = 0
            for i, flag in enumerate(key.data):
                if not flag:
                    continue
                self.data[i] = incoming[cursor] if incoming is not None else _num(value)
                cursor += 1
            return
        if isinstance(key, slice):
            indexes = range(*key.indices(len(self.data)))
            if isinstance(value, Array):
                if len(value) != len(indexes):
                    raise ValueError("slice assignment length mismatch")
                for offset, index in enumerate(indexes):
                    self.data[index] = value.data[offset]
            else:
                scalar = NAN if _is_nan(value) else _num(value)
                for index in indexes:
                    self.data[index] = scalar
            return
        self.data[key] = value.data[0] if isinstance(value, Array) else (NAN if _is_nan(value) else _num(value) if not isinstance(value, bool) else float(value))

    def _binary(self, other, op, bool_result=False):
        if isinstance(other, Array):
            if len(other) != len(self):
                raise ValueError("array length mismatch")
            values = [op(left, right) for left, right in zip(self.data, other.data)]
        else:
            scalar = other
            values = [op(left, scalar) for left in self.data]
        return Array(values, bool_=bool_result)

    def __add__(self, other):
        return self._binary(other, lambda a, b: a + b)

    def __radd__(self, other):
        return self + other

    def __sub__(self, other):
        return self._binary(other, lambda a, b: a - b)

    def __rsub__(self, other):
        return self._binary(other, lambda a, b: b - a)

    def __mul__(self, other):
        return self._binary(other, lambda a, b: a * b)

    def __rmul__(self, other):
        return self * other

    def __truediv__(self, other):
        def divide(a, b):
            if b == 0:
                return NAN if a == 0 or _is_nan(a) else math.copysign(float("inf"), a if a else 1)
            return a / b
        return self._binary(other, divide)

    def __rtruediv__(self, other):
        return self._binary(other, lambda a, b: b / a if a else NAN)

    def __itruediv__(self, other):
        result = self / other
        self.data = result.data
        return self

    def __pow__(self, other):
        return self._binary(other, lambda a, b: a ** b)

    def __neg__(self):
        return Array((-item for item in self.data))

    def __lt__(self, other):
        return self._binary(other, lambda a, b: a < b, bool_result=True)

    def __le__(self, other):
        return self._binary(other, lambda a, b: a <= b, bool_result=True)

    def __gt__(self, other):
        return self._binary(other, lambda a, b: a > b, bool_result=True)

    def __ge__(self, other):
        return self._binary(other, lambda a, b: a >= b, bool_result=True)

    def __eq__(self, other):
        return self._binary(other, lambda a, b: a == b, bool_result=True)

    def __and__(self, other):
        return self._binary(other, lambda a, b: bool(a) and bool(b), bool_result=True)

    def __or__(self, other):
        return self._binary(other, lambda a, b: bool(a) or bool(b), bool_result=True)

    def __invert__(self):
        return Array((not item for item in self.data), bool_=True)


def asarray(values, dtype=None):
    if isinstance(values, Array):
        return values.copy()
    return Array(values)


def full(n, value):
    return Array([value] * int(n))


def ones(n):
    return full(n, 1.0)


def zeros(n):
    return full(n, 0.0)


def arange(start, stop=None, step=1, dtype=None):
    if stop is None:
        stop = start
        start = 0
    return Array(range(int(start), int(stop), int(step)))


def isnan(values):
    if not isinstance(values, Array):
        return _is_nan(values)
    return Array((_is_nan(item) for item in values.data), bool_=True)


def isfinite(values):
    if not isinstance(values, Array):
        return math.isfinite(values)
    return Array((math.isfinite(item) for item in values.data), bool_=True)


def nan_to_num(values, nan=0.0):
    values = asarray(values)
    return Array((nan if _is_nan(item) else item for item in values.data))


def nanmean(values):
    values = asarray(values)
    clean = [item for item in values.data if not _is_nan(item)]
    if not clean:
        return NAN
    return _bsum(clean) / len(clean)


def mean(values):
    values = asarray(values)
    if _bany(_is_nan(item) for item in values.data) or not values.data:
        return NAN
    return _bsum(values.data) / len(values.data)


def sum_(values):
    values = asarray(values)
    if _bany(_is_nan(item) for item in values.data):
        return NAN
    return float(_bsum(values.data))


def min_(values):
    values = asarray(values)
    clean = [item for item in values.data if not _is_nan(item)]
    return _bmin(clean) if clean else NAN


def max_(values):
    values = asarray(values)
    clean = [item for item in values.data if not _is_nan(item)]
    return _bmax(clean) if clean else NAN


def std(values, ddof=0):
    values = asarray(values)
    if _bany(_is_nan(item) for item in values.data) or len(values) - ddof <= 0:
        return NAN
    avg = _bsum(values.data) / len(values.data)
    var = _bsum((item - avg) ** 2 for item in values.data) / (len(values.data) - ddof)
    return math.sqrt(var)


def _apply(values, fn):
    if not isinstance(values, Array):
        return fn(values)
    return Array((NAN if _is_nan(item) else fn(item) for item in values.data))


def sqrt(values):
    return _apply(values, math.sqrt)


def log(values):
    return _apply(values, math.log)


def log10(values):
    return _apply(values, math.log10)


def exp(values):
    return _apply(values, math.exp)


def cos(values):
    return _apply(values, math.cos)


def sign(values):
    def _sign(item):
        if item > 0:
            return 1.0
        if item < 0:
            return -1.0
        return 0.0
    return _apply(values, _sign)


def absolute(values):
    return _apply(values, _babs)


abs = absolute


def clip(values, low, high):
    values = asarray(values)
    return Array((_bmin(_bmax(item, low), high) for item in values.data))


def where(cond, x=None, y=None):
    cond = asarray(cond)
    if x is None and y is None:
        indexes = [i for i, flag in enumerate(cond.data) if flag]
        return (Array(indexes),)
    x_arr = x if isinstance(x, Array) else None
    y_arr = y if isinstance(y, Array) else None
    out = []
    for i, flag in enumerate(cond.data):
        chosen = x_arr.data[i] if flag and x_arr is not None else (x if flag else (y_arr.data[i] if y_arr is not None else y))
        out.append(chosen)
    return Array(out)


def diff(values, prepend=None):
    values = asarray(values)
    if prepend is None:
        return Array((values.data[i] - values.data[i - 1] for i in range(1, len(values))))
    base = [_num(prepend), *values.data]
    return Array((base[i] - base[i - 1] for i in range(1, len(base))))


def roll(values, shift):
    values = asarray(values)
    n = len(values)
    if n == 0:
        return values.copy()
    shift = int(shift) % n
    if shift == 0:
        return values.copy()
    return Array(values.data[-shift:] + values.data[:-shift])


def cumsum(values):
    values = asarray(values)
    total = 0.0
    out = []
    for item in values.data:
        total += 0.0 if _is_nan(item) else item
        out.append(total)
    return Array(out)


def dot(left, right):
    left = asarray(left)
    right = asarray(right)
    return float(_bsum(a * b for a, b in zip(left.data, right.data)))


def maximum(left, right=None):
    if right is None:
        return max_(left)
    return where(asarray(left) >= right if not isinstance(right, Array) else asarray(left) >= right, left, right)


def minimum(left, right):
    return where(asarray(left) <= right, left, right)


def _accumulate(values):
    values = asarray(values)
    best = -float("inf")
    out = []
    for item in values.data:
        best = item if item > best else best
        out.append(best)
    return Array(out)


maximum.accumulate = _accumulate


def argmax(values):
    values = asarray(values)
    best_i = 0
    best = -float("inf")
    for i, item in enumerate(values.data):
        if item > best:
            best = item
            best_i = i
    return best_i


def argmin(values):
    values = asarray(values)
    best_i = 0
    best = float("inf")
    for i, item in enumerate(values.data):
        if item < best:
            best = item
            best_i = i
    return best_i


ndarray = Array

sum = sum_
max = max_
min = min_
