"""A small program builder: named groups of variables, rows of `sum(coef x var) <= rhs`, one equality.

Linear by default, solved with scipy's HiGHS. A group may carry a quadratic cost (cost x + 1/2 quad x^2 per variable);
the program is then a convex quadratic program and is solved with HiGHS through `highspy`."""
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix


class Program:
    def __init__(self):
        self.var = {}                      # group name -> (start, length)
        self._cost, self._ub, self._quad = [], [], []
        self.n = 0
        self._r, self._c, self._v, self._b = [], [], [], []
        self.rows = 0
        self._lower, self._upper = {}, {}     # bounds set after building: variable index -> value

    def add(self, name, cost, upper, quad=None):
        """A group of variables, each in [0, upper], costing cost x + 1/2 quad x^2. -> index of the first one."""
        cost, upper = np.asarray(cost, float), np.asarray(upper, float)
        self.var[name] = (self.n, len(cost))
        self._cost.append(cost)
        self._ub.append(upper)
        self._quad.append(np.zeros(len(cost)) if quad is None else np.asarray(quad, float))
        self.n += len(cost)
        return self.var[name][0]

    def start(self, name):
        return self.var[name][0]

    def row(self, cols, vals, rhs):
        """sum(vals x variables[cols]) <= rhs. -> the row's index (its dual is read back by that index)."""
        self._r.extend([self.rows] * len(cols))
        self._c.extend(cols)
        self._v.extend(vals)
        self._b.append(rhs)
        self.rows += 1
        return self.rows - 1

    def pin(self, lower=None, upper=None):
        """Tighten bounds on single variables: {index: new lower bound}, {index: new upper bound}."""
        self._lower.update(lower or {})
        self._upper.update(upper or {})

    def solve(self, eq, eq_rhs, method='highs', options=None):
        """Minimize cost subject to the rows and `eq @ x == eq_rhs`. -> a result with x, fun, status, message,
        eqlin.marginals and ineqlin.marginals (scipy's, or the same shape from the quadratic solve)."""
        c, ub = np.concatenate(self._cost), np.concatenate(self._ub)
        quad = np.concatenate(self._quad)
        lb = np.zeros(self.n)
        for k, v in self._upper.items():
            ub[k] = v
        for k, v in self._lower.items():
            lb[k] = v
        A = coo_matrix((self._v, (self._r, self._c)), shape=(self.rows, self.n)).tocsr() if self.rows else None
        if (quad > 0).any():
            return _quadratic(c, quad, A, np.array(self._b), eq, eq_rhs, lb, ub)
        return linprog(c, A_ub=A, b_ub=np.array(self._b) if self.rows else None, A_eq=eq[None, :], b_eq=[eq_rhs],
                       bounds=list(zip(lb, ub)), method=method, options=options or None)


class _Marginals:
    def __init__(self, marginals):
        self.marginals = marginals


class _Solution:
    def __init__(self, x, fun, status, message, eq_dual, row_duals):
        self.x, self.fun, self.status, self.message = x, fun, status, message
        self.eqlin, self.ineqlin = _Marginals(np.array([eq_dual])), _Marginals(row_duals)


def _quadratic(c, quad, A, b, eq, eq_rhs, lb, ub):
    """min c x + 1/2 sum(quad x^2)  s.t.  A x <= b,  eq x == eq_rhs,  lb <= x <= ub, with HiGHS."""
    try:
        import highspy
    except ImportError as e:                                             # pragma: no cover
        raise ImportError('sloped offer curves solved exactly (rules.offer_curves="exact") need the highspy package: '
                          'pip install highspy. Or use rules.offer_curves="steps"') from e
    from scipy.sparse import csc_matrix, vstack
    n, m = len(c), (A.shape[0] if A is not None else 0)
    M = (vstack([A, csc_matrix(eq[None, :])]) if A is not None else csc_matrix(eq[None, :])).tocsc()
    inf = highspy.kHighsInf
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = n, m + 1
    lp.col_cost_ = c
    lp.col_lower_, lp.col_upper_ = lb, np.where(np.isfinite(ub), ub, inf)
    lp.row_lower_ = np.r_[np.full(m, -inf), eq_rhs]
    lp.row_upper_ = np.r_[np.where(np.isfinite(b), b, inf) if m else np.zeros(0), eq_rhs]
    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_, lp.a_matrix_.index_, lp.a_matrix_.value_ = M.indptr, M.indices, M.data
    h = highspy.Highs()
    h.silent()
    h.passModel(lp)
    hess = highspy.HighsHessian()
    hess.dim_, hess.format_ = n, highspy.HessianFormat.kTriangular
    on = quad > 0
    hess.start_ = np.r_[0, np.cumsum(on)].astype(np.int32)
    hess.index_, hess.value_ = np.where(on)[0].astype(np.int32), quad[on]
    h.passHessian(hess)
    h.run()
    ok = h.getModelStatus() == highspy.HighsModelStatus.kOptimal
    sol = h.getSolution()
    x, duals = np.array(sol.col_value), np.array(sol.row_dual)
    return _Solution(x, float(h.getInfo().objective_function_value), 0 if ok else 1, h.modelStatusToString(h.getModelStatus()),
                     duals[m] if len(duals) > m else np.nan, duals[:m])
