import { Pause, Play, SkipBack, SkipForward } from 'lucide-react';

export default function PlayerControls({ playing, fps, onToggle, onPrev, onNext, onFpsChange }) {
  function clampFps(value) {
    return Math.min(120, Math.max(1, Number(value) || 1));
  }

  return (
    <div className="controls-row">
      <button className="icon-button" onClick={onPrev} title="Previous frame (←)" aria-label="Previous frame"><SkipBack size={18} /></button>
      <button className="primary-button" onClick={onToggle} title="Play / Pause (Space)" aria-label={playing ? 'Pause' : 'Play'}>
        {playing ? <Pause size={18} /> : <Play size={18} />}
        <span>{playing ? 'Pause' : 'Play'}</span>
      </button>
      <button className="icon-button" onClick={onNext} title="Next frame (→)" aria-label="Next frame"><SkipForward size={18} /></button>
      <label className="fps-control">
        <span>FPS</span>
        <input type="number" min="1" max="120" value={fps} onChange={(event) => onFpsChange(clampFps(event.target.value))} />
      </label>
    </div>
  );
}
