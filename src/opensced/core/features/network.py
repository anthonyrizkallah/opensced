"""Transmission constraints.

    flow + sum over resources of shift factor x (MW - output) <= limit + violation       (its dual is the shadow price)

`flow` is the flow on the element with every resource at its `output`. A violation costs the constraint's
max_shadow_price per MW, so a constraint nothing can relieve prices at that cap instead of making the program
infeasible. A node's price is lambda - sum(shift factor x shadow price).
"""
import numpy as np
import pandas as pd


def resource_shift_factors(shift_factors, resource_nodes):
    """Node shift factors (constraint x node) and a resource -> node map -> shift factors per resource (constraint x
    resource). resource_nodes: Series or dict resource -> node, or DataFrame resource, node[, share]. A resource split
    over several nodes takes the share-weighted mean. A resource on a node with no column gets 0."""
    if isinstance(resource_nodes, pd.DataFrame):
        m = resource_nodes.copy()
        m['share'] = pd.to_numeric(m['share']) if 'share' in m else 1.0
    else:
        s = pd.Series(resource_nodes)
        m = pd.DataFrame({'resource': s.index, 'node': s.to_numpy(), 'share': 1.0})
    m['node'] = m['node'].astype(str)
    cols = pd.Index(shift_factors.columns.astype(str))
    m = m[m['node'].isin(cols)]
    S = shift_factors.to_numpy(float)
    pos = cols.get_indexer(m['node'])
    W = pd.DataFrame(S[:, pos] * m['share'].to_numpy(float), index=shift_factors.index, columns=m['resource'].to_numpy())
    tot = m.groupby('resource', sort=False)['share'].sum()
    out = W.T.groupby(level=0, sort=False).sum().T
    return out / tot.reindex(out.columns).to_numpy()


def unmapped(inputs):
    """Resources that will not affect any constraint: not in resource_nodes, or on a node with no shift factors."""
    names = inputs.resources['name']
    if inputs.shift_factors is None:
        return list(names)
    sf = inputs.shift_factors if inputs.resource_nodes is None else resource_shift_factors(inputs.shift_factors, inputs.resource_nodes)
    return [n for n in names if n not in sf.columns]


def matrix(S, inputs, cutoff=0.0):
    """-> the constraints table and the shift-factor matrix constraints x resources, or (None, None)."""
    c = inputs.constraints
    if c is None or not len(c):
        return None, None
    sf = inputs.shift_factors if inputs.resource_nodes is None else resource_shift_factors(inputs.shift_factors, inputs.resource_nodes)
    M = sf.reindex(index=c['name'].to_numpy(), columns=S['names']).fillna(0.0).to_numpy(float)
    if cutoff > 0:                                                       # too small to count in the dispatch
        M = np.where(np.abs(M) < cutoff, 0.0, M)
    return c.reset_index(drop=True), M


def variables(P, S):
    c = S['cons']
    P.add('violation', pd.to_numeric(c['max_shadow_price']).to_numpy(float), np.full(len(c), np.inf))


def rows(P, S):
    c, sf = S['cons'], S['sf']
    lim, flow = pd.to_numeric(c['limit']).to_numpy(float), pd.to_numeric(c['flow']).to_numpy(float)
    by_block = sf[:, S['B'].res.to_numpy()]
    at_output, at_floor = sf @ S['output'], sf @ S['lo']
    v = P.start('violation')
    S['net_rows'] = []
    for j in range(len(c)):
        nz = np.where(np.abs(by_block[j]) > 1e-12)[0]
        S['net_rows'].append(P.row(list(nz) + [v + j], list(by_block[j, nz]) + [-1.0], lim[j] - flow[j] + at_output[j] - at_floor[j]))
