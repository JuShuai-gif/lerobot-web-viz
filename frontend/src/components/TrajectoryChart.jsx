import { useMemo, useState } from 'react';
import { Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

function colorHSL(h, s, l) {
  return `hsl(${h}, ${s}%, ${l}%)`;
}

function makeColors(dims, h, s, lStart, lEnd) {
  const step = dims > 1 ? (lEnd - lStart) / (dims - 1) : 0;
  return Array.from({ length: dims }, (_, i) => colorHSL(h, s, lStart + i * step));
}

const ACTION_COLORS = [215, 70];
const STATE_COLORS = [160, 60];
const MAX_SELECTED = 12;

export default function TrajectoryChart({
  actions, states, actionNames, stateNames,
  currentFrame, onSelectFrame,
}) {
  const [selected, setSelected] = useState(new Set());

  const actionDims = useMemo(() => {
    const n = actions?.find(Array.isArray)?.length || 0;
    const names = actionNames || [];
    return Array.from({ length: n }, (_, i) => ({
      key: `A_${i}`,
      label: names[i] || `dim ${i}`,
      group: 'action',
      colorIdx: i,
    }));
  }, [actions, actionNames]);

  const stateDims = useMemo(() => {
    const n = states?.find(Array.isArray)?.length || 0;
    const names = stateNames || [];
    return Array.from({ length: n }, (_, i) => ({
      key: `S_${i}`,
      label: names[i] || `dim ${i}`,
      group: 'state',
      colorIdx: i,
    }));
  }, [states, stateNames]);

  const allDims = useMemo(() => [...actionDims, ...stateDims], [actionDims, stateDims]);

  const aColors = useMemo(() => makeColors(actionDims.length, ...ACTION_COLORS, 30, 70), [actionDims.length]);
  const sColors = useMemo(() => makeColors(stateDims.length, ...STATE_COLORS, 25, 65), [stateDims.length]);

  const colorMap = useMemo(() => {
    const map = {};
    actionDims.forEach((d) => { map[d.key] = aColors[d.colorIdx]; });
    stateDims.forEach((d) => { map[d.key] = sColors[d.colorIdx]; });
    return map;
  }, [actionDims, stateDims, aColors, sColors]);

  const chartData = (() => {
    const aLen = (actions || []).length;
    const sLen = (states || []).length;
    const maxLen = Math.max(aLen, sLen);
    const sel = selected;
    const result = [];
    for (let frame = 0; frame < maxLen; frame++) {
      const row = { frame };
      sel.forEach((key) => {
        const [group, idx] = key.split('_');
        const arr = group === 'A' ? actions : states;
        const val = arr?.[frame]?.[Number(idx)];
        row[key] = Number.isFinite(val) ? val : null;
      });
      result.push(row);
    }
    return result;
  })();

  const stats = useMemo(() => {
    const result = [];
    for (const key of selected) {
      const [group, idx] = key.split('_');
      const arr = group === 'A' ? actions : states;
      const vals = (arr || []).map((f) => f?.[Number(idx)]).filter((v) => Number.isFinite(v));
      if (vals.length === 0) continue;
      const min = Math.min(...vals);
      const max = Math.max(...vals);
      const mean = vals.reduce((s, v) => s + v, 0) / vals.length;
      const dim = allDims.find((d) => d.key === key);
      const current = arr?.[currentFrame]?.[Number(idx)];
      result.push({
        key,
        label: dim?.label || key,
        group: group === 'A' ? 'A' : 'S',
        min, max, mean,
        current: Number.isFinite(current) ? current : null,
      });
    }
    return result;
  }, [actions, states, selected, currentFrame, allDims]);

  function toggle(key) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else if (next.size < MAX_SELECTED) {
        next.add(key);
      }
      return next;
    });
  }

  function toggleGroup(group) {
    const dims = group === 'action' ? actionDims : stateDims;
    const keys = dims.map((d) => d.key);
    const hasAny = keys.some((k) => selected.has(k));
    setSelected((prev) => {
      const next = new Set(prev);
      if (hasAny) {
        keys.forEach((k) => next.delete(k));
      } else {
        keys.forEach((k) => { if (next.size < MAX_SELECTED) next.add(k); });
      }
      return next;
    });
  }

  function shortLabel(label) {
    const parts = label.split('_');
    return parts[parts.length - 1];
  }

  if (allDims.length === 0) return (
    <div className="trajectory-chart">
      <div className="chart-header"><div className="panel-title">Trajectory</div></div>
      <div className="chart-empty">No trajectory data — click Load trajectories</div>
    </div>
  );

  return (
    <div className="trajectory-chart">
      <div className="chart-header">
        <div className="panel-title">Trajectory</div>
        <span className="dim-hint">{selected.size} / {MAX_SELECTED} dims</span>
      </div>

      <div className="checkbox-groups">
        {actionDims.length > 0 && (
          <div className="checkbox-group">
            <label className="group-toggle">
              <input type="checkbox"
                checked={actionDims.every((d) => selected.has(d.key))}
                ref={(el) => { if (el) el.indeterminate = actionDims.some((d) => selected.has(d.key)) && !actionDims.every((d) => selected.has(d.key)); }}
                onChange={() => toggleGroup('action')}
              />
              <strong>Action</strong>
            </label>
            <div className="dim-list">
              {actionDims.map((d) => (
                <label key={d.key} className="dim-checkbox" title={d.label}>
                  <input type="checkbox" checked={selected.has(d.key)} onChange={() => toggle(d.key)} />
                  <span className="dim-color" style={{ background: aColors[d.colorIdx] }} />
                  <span>{shortLabel(d.label)}</span>
                </label>
              ))}
            </div>
          </div>
        )}
        {stateDims.length > 0 && (
          <div className="checkbox-group">
            <label className="group-toggle">
              <input type="checkbox"
                checked={stateDims.every((d) => selected.has(d.key))}
                ref={(el) => { if (el) el.indeterminate = stateDims.some((d) => selected.has(d.key)) && !stateDims.every((d) => selected.has(d.key)); }}
                onChange={() => toggleGroup('state')}
              />
              <strong>State</strong>
            </label>
            <div className="dim-list">
              {stateDims.map((d) => (
                <label key={d.key} className="dim-checkbox" title={d.label}>
                  <input type="checkbox" checked={selected.has(d.key)} onChange={() => toggle(d.key)} />
                  <span className="dim-color" style={{ background: sColors[d.colorIdx] }} />
                  <span>{shortLabel(d.label)}</span>
                </label>
              ))}
            </div>
          </div>
        )}
      </div>

      {selected.size > 0 && (
        <>
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={chartData} onClick={(event) => event?.activeLabel != null && onSelectFrame(Number(event.activeLabel))}>
              <XAxis dataKey="frame" type="number" domain={[0, Math.max(0, (chartData.length || 1) - 1)]} tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} width={44} />
              <Tooltip labelFormatter={(label) => `frame ${label}`} />
              {[...selected].map((key) => (
                <Line key={key} type="monotone" dataKey={key} dot={false} stroke={colorMap[key]} strokeWidth={1.5} isAnimationActive={false} connectNulls={false} />
              ))}
              <ReferenceLine x={currentFrame} stroke="#111827" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>

          <div className="chart-stats">
            {stats.map((s) => (
              <span key={s.key}>
                <span className="dim-color" style={{ background: colorMap[s.key] }} />
                <small>{s.label} {s.group}</small>
                <small>{s.current != null ? s.current.toFixed(4) : '--'}</small>
                <small>{s.min.toFixed(3)}..{s.max.toFixed(3)}</small>
              </span>
            ))}
          </div>
        </>
      )}
      {selected.size === 0 && (
        <div className="chart-empty">Select dimensions to plot</div>
      )}
    </div>
  );
}
