import { Pause, Play, SkipBack, SkipForward } from 'lucide-react';

export default function PlayerControls({ playing, fps, onToggle, onPrev, onNext, onFpsChange }) {
  return (
    <div className="controls-row">
      <button className="icon-button" onClick={onPrev} title="Previous frame"><SkipBack size={18} /></button>
      <button className="primary-button" onClick={onToggle} title="Play or pause">
        {playing ? <Pause size={18} /> : <Play size={18} />}
        <span>{playing ? 'Pause' : 'Play'}</span>
      </button>
      <button className="icon-button" onClick={onNext} title="Next frame"><SkipForward size={18} /></button>
      <label className="fps-control">
        <span>FPS</span>
        <input type="number" min="1" max="120" value={fps} onChange={(event) => onFpsChange(Number(event.target.value) || 1)} />
      </label>
    </div>
  );
}
