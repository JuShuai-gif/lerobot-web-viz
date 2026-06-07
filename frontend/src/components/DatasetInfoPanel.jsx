export default function DatasetInfoPanel({ datasetInfo, episode, warnings }) {
  return (
    <aside className="info-panel">
      <div className="panel-title">Warnings</div>
      <div className="warning-list">
        {(warnings || []).length === 0 && <div className="warning empty">No warnings</div>}
        {(warnings || []).map((warning, index) => (
          <div className={`warning ${warning.level}`} key={`${warning.type}-${index}`}>
            <strong>{warning.type}</strong>
            <span>{warning.message}</span>
          </div>
        ))}
      </div>
      <div className="panel-title">Dataset</div>
      <dl className="info-list">
        <dt>Repo</dt><dd>{datasetInfo?.repo_id || '--'}</dd>
        <dt>FPS</dt><dd>{datasetInfo?.fps || '--'}</dd>
        <dt>Frames</dt><dd>{datasetInfo?.total_frames ?? '--'}</dd>
        <dt>Episodes</dt><dd>{datasetInfo?.total_episodes ?? '--'}</dd>
        <dt>Cameras</dt><dd>{datasetInfo?.camera_keys?.join(', ') || '--'}</dd>
        <dt>Features</dt><dd className="features-tags">{datasetInfo?.feature_keys?.map((key) => <code key={key}>{key}</code>) || '--'}</dd>
        {datasetInfo?.action_stats && (
          <>
            <dt>Action range</dt>
            <dd className="stat-range">
              {datasetInfo.action_names?.map((name, i) => (
                <span key={name} title={`${name}: min=${datasetInfo.action_stats.min?.[i]?.toFixed(3)}, max=${datasetInfo.action_stats.max?.[i]?.toFixed(3)}`}>
                  {name.split('_').pop()} <small>{datasetInfo.action_stats.min?.[i]?.toFixed(2)}..{datasetInfo.action_stats.max?.[i]?.toFixed(2)}</small>
                </span>
              ))}
            </dd>
          </>
        )}
        {datasetInfo?.state_stats && (
          <>
            <dt>State range</dt>
            <dd className="stat-range">
              {datasetInfo.state_names?.map((name, i) => (
                <span key={name} title={`${name}: min=${datasetInfo.state_stats.min?.[i]?.toFixed(3)}, max=${datasetInfo.state_stats.max?.[i]?.toFixed(3)}`}>
                  {name.split('_').pop()} <small>{datasetInfo.state_stats.min?.[i]?.toFixed(2)}..{datasetInfo.state_stats.max?.[i]?.toFixed(2)}</small>
                </span>
              ))}
            </dd>
          </>
        )}
        <dt>Current</dt><dd>{episode ? `#${episode.id}, ${episode.frame_count} frames` : '--'}</dd>
        {episode?.tasks?.length > 0 && <><dt>Task</dt><dd>{episode.tasks.join(', ')}</dd></>}
      </dl>
    </aside>
  );
}
