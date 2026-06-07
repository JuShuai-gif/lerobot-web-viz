import { useRef } from 'react';

export default function Timeline({ frameId, frameCount, timestamp, onChange }) {
  const maxFrame = Math.max(0, frameCount - 1);
  const rafRef = useRef(null);
  const pendingRef = useRef(null);

  function handleInput(event) {
    const value = Number(event.target.value);
    pendingRef.current = value;
    if (rafRef.current == null) {
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        if (pendingRef.current != null) {
          onChange(pendingRef.current);
        }
      });
    }
  }

  return (
    <div className="timeline-row">
      <input
        type="range"
        min="0"
        max={maxFrame}
        value={Math.min(frameId, maxFrame)}
        onInput={handleInput}
      />
      <div className="timeline-meta">
        <span>{frameId}/{maxFrame}</span>
        <span>{timestamp == null ? '--' : `${timestamp.toFixed(3)}s`}</span>
      </div>
    </div>
  );
}
