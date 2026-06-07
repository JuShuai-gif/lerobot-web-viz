export default function Timeline({ frameId, frameCount, timestamp, onChange }) {
  const maxFrame = Math.max(0, frameCount - 1);
  return (
    <div className="timeline-row">
      <input
        type="range"
        min="0"
        max={maxFrame}
        value={Math.min(frameId, maxFrame)}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <div className="timeline-meta">
        <span>{frameId}/{maxFrame}</span>
        <span>{timestamp == null ? '--' : `${timestamp.toFixed(3)}s`}</span>
      </div>
    </div>
  );
}
