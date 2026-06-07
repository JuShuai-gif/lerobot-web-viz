import { memo } from 'react';
import { Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

function numericValues(values, dim) {
  return (values || [])
    .map((value, frame) => ({ frame, value: Array.isArray(value) ? value[dim] : null }))
    .filter((row) => Number.isFinite(row.value));
}

function statsFor(values, dim, currentFrame) {
  const rows = numericValues(values, dim);
  if (rows.length === 0) return null;
  const nums = rows.map((row) => row.value);
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const mean = nums.reduce((sum, value) => sum + value, 0) / nums.length;
  const variance = nums.reduce((sum, value) => sum + (value - mean) ** 2, 0) / nums.length;
  const current = Array.isArray(values?.[currentFrame]) ? values[currentFrame][dim] : null;
  return { min, max, mean, std: Math.sqrt(variance), current, count: rows.length };
}

function toRows(values, dim) {
  return (values || []).map((value, frame) => ({
    frame,
    value: Array.isArray(value) && Number.isFinite(value[dim]) ? value[dim] : null,
  }));
}

const SeriesChart = memo(function SeriesChart({ title, values, currentFrame, selectedDim, onDimChange, onSelectFrame, color, dimNames }) {
  const dims = values?.find((item) => Array.isArray(item))?.length || 0;
  const safeDim = Math.min(Math.max(0, selectedDim || 0), Math.max(0, dims - 1));
  const rows = toRows(values, safeDim);
  const stats = statsFor(values, safeDim, currentFrame);

  function dimLabel(index) {
    if (dimNames && index < dimNames.length) return dimNames[index];
    return `dim ${index}`;
  }

  return (
    <div className="chart-panel">
      <div className="chart-header">
        <div className="panel-title">{title}</div>
        {dims > 1 && (
          <select value={safeDim} onChange={(event) => onDimChange(Number(event.target.value))}>
            {Array.from({ length: dims }).map((_, index) => (
              <option key={index} value={index}>{dimLabel(index)}</option>
            ))}
          </select>
        )}
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={rows} onClick={(event) => event?.activeLabel != null && onSelectFrame(Number(event.activeLabel))}>
          <XAxis dataKey="frame" type="number" domain={[0, Math.max(0, rows.length - 1)]} tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} width={42} />
          <Tooltip labelFormatter={(label) => `frame ${label}`} />
          <Line type="monotone" dataKey="value" dot={false} stroke={color} strokeWidth={1.7} isAnimationActive={false} connectNulls={false} />
          <ReferenceLine x={currentFrame} stroke="#111827" strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
      <div className="chart-stats">
        {stats ? (
          <>
            <span>current {Number.isFinite(stats.current) ? stats.current.toFixed(4) : '--'}</span>
            <span>min {stats.min.toFixed(4)}</span>
            <span>max {stats.max.toFixed(4)}</span>
            <span>mean {stats.mean.toFixed(4)}</span>
            <span>std {stats.std.toFixed(4)}</span>
            <span>n {stats.count}</span>
          </>
        ) : <span>No numeric data</span>}
      </div>
    </div>
  );
});

export default SeriesChart;
