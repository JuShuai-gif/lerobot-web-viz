import { useEffect, useState } from 'react';
import { getAnalysis } from '../api/client.js';

export default function DatasetInfoPanel({ datasetInfo, episode, warnings, onNavigateToFrame }) {
  const [analysis, setAnalysis] = useState(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);

  useEffect(() => {
    if (!datasetInfo) return;
    setAnalysisLoading(true);
    getAnalysis()
      .then((data) => setAnalysis(data))
      .catch(() => setAnalysis(null))
      .finally(() => setAnalysisLoading(false));
  }, [datasetInfo?.dataset_path]);

  return (
    <aside className="info-panel">
      <div className="panel-title">Warnings</div>
      <div className="warning-list warning-section">
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

      {datasetInfo && (
        <div className="analysis-section">
          <div className="panel-title">分析报告</div>
          {analysisLoading ? (
            <div className="analysis-loading"><span className="spinner" /> 分析中...</div>
          ) : analysis ? (
            <div className="analysis-body">
              <pre className="analysis-summary">{analysis.summary}</pre>
              {analysis.action_jumps?.length > 0 && (
                <details className="analysis-detail">
                  <summary>动作跳变 ({analysis.action_jumps.length} 处)</summary>
                  <ul>
                    {analysis.action_jumps.map((j, i) => (
                      <li key={i} className="clickable-detail" onClick={() => onNavigateToFrame && onNavigateToFrame(j.episode, j.from_frame)}>
                        Ep {j.episode} 帧 {j.from_frame} → {j.to_frame} z={j.zscore}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {analysis.fps_deviations?.length > 0 && (
                <details className="analysis-detail">
                  <summary>帧率异常 ({analysis.fps_deviations.length} 段)</summary>
                  <ul>
                    {analysis.fps_deviations.map((d, i) => (
                      <li key={i} className="clickable-detail" onClick={() => onNavigateToFrame && onNavigateToFrame(d.episode, 0)}>Ep {d.episode}: 实际 {d.actual}fps vs 标称 {d.nominal}fps</li>
                    ))}
                  </ul>
                </details>
              )}
              {analysis.frame_gaps?.length > 0 && (
                <details className="analysis-detail">
                  <summary>帧索引缺失 ({analysis.frame_gaps.length} 处)</summary>
                  <ul>
                    {analysis.frame_gaps.map((g, i) => (
                      <li key={i} className="clickable-detail" onClick={() => onNavigateToFrame && onNavigateToFrame(g.episode, g.position)}>Ep {g.episode} 位置 {g.position} 缺失 {g.gap} 帧</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          ) : (
            <div className="analysis-error">分析失败</div>
          )}
        </div>
      )}
    </aside>
  );
}
