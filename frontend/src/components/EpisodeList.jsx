export default function EpisodeList({ episodes, selectedId, onSelect }) {
  return (
    <aside className="episode-list">
      <div className="panel-title">Episodes</div>
      <div className="episode-scroll">
        {episodes.map((episode) => (
          <button
            key={episode.id}
            className={episode.id === selectedId ? 'episode-item selected' : 'episode-item'}
            onClick={() => onSelect(episode.id)}
          >
            <span>#{episode.id}</span>
            <small>{episode.frame_count} fr{episode.duration != null ? ` · ${episode.duration}s` : ''}</small>
            {episode.tasks?.length > 0 && <small className="episode-task">{episode.tasks.join(', ')}</small>}
          </button>
        ))}
      </div>
    </aside>
  );
}
