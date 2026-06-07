import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getEpisode, getEpisodeVideos, getEpisodes, getFeatureSeries, getFrameUrl, getTrajectories, loadDataset, nativePickFolder } from './api/client.js';
import TrajectoryChart from './components/TrajectoryChart.jsx';
import DatasetInfoPanel from './components/DatasetInfoPanel.jsx';
import EpisodeList from './components/EpisodeList.jsx';
import FeatureViewer from './components/FeatureViewer.jsx';
import MultiCameraViewer from './components/MultiCameraViewer.jsx';
import PlayerControls from './components/PlayerControls.jsx';
import Timeline from './components/Timeline.jsx';

const PRELOAD_AHEAD = 8;
const MAX_IMAGE_CACHE = 240;
const MAX_PRELOAD_CONCURRENT = 4;
const JPEG_QUALITY = 75;
const SYNC_TOLERANCE_SECONDS = 0.08;

function firstNumericTimestamp(timestamps) {
  const value = (timestamps || []).find((item) => Number.isFinite(item));
  return Number.isFinite(value) ? value : 0;
}

export default function App() {
  const [datasetInfo, setDatasetInfo] = useState(null);
  const [episodes, setEpisodes] = useState([]);
  const [selectedEpisodeId, setSelectedEpisodeId] = useState(null);
  const [episode, setEpisode] = useState(null);
  const [frameId, setFrameId] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [fps, setFps] = useState(30);
  const [actions, setActions] = useState([]);
  const [states, setStates] = useState([]);
  const [timestamps, setTimestamps] = useState([]);
  const [warnings, setWarnings] = useState([]);
  const [videoSegments, setVideoSegments] = useState([]);
  const [loadingTrajectories, setLoadingTrajectories] = useState(false);
  const [trajectoriesLoaded, setTrajectoriesLoaded] = useState(false);
  const [taskIndices, setTaskIndices] = useState([]);
  const [error, setError] = useState('');
  const [datasetPathInput, setDatasetPathInput] = useState('');
  const [repoIdInput, setRepoIdInput] = useState('');
  const [loadingDataset, setLoadingDataset] = useState(false);
  const [episodeLoading, setEpisodeLoading] = useState(false);
  const rafRef = useRef(null);
  const lastTickRef = useRef(0);
  const imageCacheRef = useRef(new Map());
  const videoRefs = useRef({});
  const [videoReadyMap, setVideoReadyMap] = useState({});
  const [videoStalled, setVideoStalled] = useState(false);
  const frameIdRef = useRef(0);
  const preloadQueueRef = useRef([]);
  const preloadActiveRef = useRef(0);
  const pendingNavigateRef = useRef(null);

  useEffect(() => {
    frameIdRef.current = frameId;
  }, [frameId]);

  const frameCount = episode?.frame_count || 0;
  const cameraKeys = episode?.camera_keys || datasetInfo?.camera_keys || [];
  const timestamp = timestamps[frameId];
  const hasNativeVideos = videoSegments.length > 0;
  const videoByCamera = useMemo(() => new Map(videoSegments.map((segment) => [segment.camera, segment])), [videoSegments]);
  const taskMap = datasetInfo?.task_map || {};
  const currentTaskIndex = taskIndices[frameId];
  const currentTask = (currentTaskIndex != null && taskMap[currentTaskIndex]) ? taskMap[currentTaskIndex] : (episode?.tasks?.[0] || '');
  const episodeDuration = useMemo(() => {
    const durations = videoSegments.map((segment) => segment.duration).filter((value) => value > 0);
    if (durations.length > 0) return Math.min(...durations);
    return frameCount > 0 ? frameCount / Math.max(1, fps) : 0;
  }, [frameCount, fps, videoSegments]);

  const allVideosReady = useMemo(() => {
    if (!hasNativeVideos) return false;
    return videoSegments.every((s) => videoReadyMap[s.camera]);
  }, [hasNativeVideos, videoSegments, videoReadyMap]);

  const clampFrame = useCallback((nextFrame) => {
    const maxFrame = Math.max(0, frameCount - 1);
    return Math.max(0, Math.min(maxFrame, nextFrame));
  }, [frameCount]);

  const frameToRelativeTime = useCallback((targetFrame) => {
    if (timestamps.length > targetFrame && Number.isFinite(timestamps[targetFrame])) {
      return Math.max(0, timestamps[targetFrame] - firstNumericTimestamp(timestamps));
    }
    return targetFrame / Math.max(1, fps);
  }, [fps, timestamps]);

  const relativeTimeToFrame = useCallback((relativeTime) => {
    if (timestamps.length > 1) {
      const base = firstNumericTimestamp(timestamps);
      const absolute = base + relativeTime;
      let bestFrame = 0;
      let bestDistance = Number.POSITIVE_INFINITY;
      for (let index = 0; index < timestamps.length; index += 1) {
        const value = timestamps[index];
        if (!Number.isFinite(value)) continue;
        const distance = Math.abs(value - absolute);
        if (distance < bestDistance) {
          bestDistance = distance;
          bestFrame = index;
        }
      }
      return clampFrame(bestFrame);
    }
    return clampFrame(Math.round(relativeTime * Math.max(1, fps)));
  }, [clampFrame, fps, timestamps]);

  const seekVideosToRelativeTime = useCallback((relativeTime) => {
    if (!hasNativeVideos) return;
    for (const segment of videoSegments) {
      const node = videoRefs.current[segment.camera];
      if (!node || Number.isNaN(node.duration)) continue;
      const target = Math.min(segment.to_timestamp, Math.max(segment.from_timestamp, segment.from_timestamp + relativeTime));
      if (Math.abs(node.currentTime - target) > 0.015) {
        node.currentTime = target;
      }
    }
  }, [hasNativeVideos, videoSegments]);

  const pauseVideos = useCallback(() => {
    for (const node of Object.values(videoRefs.current)) {
      node.pause();
    }
  }, []);

  const playVideos = useCallback(() => {
    for (const segment of videoSegments) {
      const node = videoRefs.current[segment.camera];
      if (!node) continue;
      const relative = frameToRelativeTime(frameIdRef.current);
      const target = segment.from_timestamp + relative;
      if (node.currentTime < segment.from_timestamp || node.currentTime >= segment.to_timestamp || Math.abs(node.currentTime - target) > SYNC_TOLERANCE_SECONDS) {
        node.currentTime = Math.min(segment.to_timestamp, Math.max(segment.from_timestamp, target));
      }
      node.playbackRate = Math.max(0.1, fps / Math.max(1, segment.fps || fps));
    }
    // Start all videos at the same time (after seeks are issued)
    setTimeout(() => {
      for (const segment of videoSegments) {
        const node = videoRefs.current[segment.camera];
        if (node) node.play().catch(() => {});
      }
    }, 0);
  }, [fps, frameToRelativeTime, videoSegments]);

  const jumpToFrame = useCallback((nextFrame) => {
    const targetFrame = clampFrame(nextFrame);
    setFrameId(targetFrame);
    seekVideosToRelativeTime(frameToRelativeTime(targetFrame));
  }, [clampFrame, frameToRelativeTime, seekVideosToRelativeTime]);

  const handleLoadDataset = useCallback((event) => {
    event.preventDefault();
    if (!datasetPathInput.trim()) {
      setError('Please enter a dataset path on the server.');
      return;
    }
    setLoadingDataset(true);
    setPlaying(false);
    pauseVideos();
    setSelectedEpisodeId(null);
    setEpisode(null);
    setEpisodes([]);
    setActions([]);
    setStates([]);
    setTimestamps([]);
    setTaskIndices([]);
    setWarnings([]);
    setVideoSegments([]);
    setVideoReadyMap({});
    setVideoStalled(false);
    setTrajectoriesLoaded(false);
    videoRefs.current = {};
    imageCacheRef.current.clear();
    loadDataset(datasetPathInput.trim(), repoIdInput.trim())
      .then((info) => {
        setDatasetInfo(info);
        setDatasetPathInput(info.dataset_path || datasetPathInput.trim());
        return getEpisodes();
      })
      .then((episodeList) => {
        setEpisodes(episodeList);
        if (episodeList.length > 0) setSelectedEpisodeId(episodeList[0].id);
        setError('');
      })
      .catch((exc) => setError(exc.message))
      .finally(() => setLoadingDataset(false));
  }, [datasetPathInput, pauseVideos, repoIdInput]);

  const handlePickFolder = useCallback(() => {
    nativePickFolder()
      .then((data) => setDatasetPathInput(data.path))
      .catch((exc) => setError(exc.message));
  }, []);

  const navigateToFrame = useCallback((episodeId, frameIndex) => {
    if (episodeId == null) return;
    pendingNavigateRef.current = { episodeId, frameIndex };
    setSelectedEpisodeId(episodeId);
  }, []);

  // Execute pending navigation once episode data is loaded
  useEffect(() => {
    if (!episode || !pendingNavigateRef.current) return;
    if (episode.id !== pendingNavigateRef.current.episodeId) return;
    const target = pendingNavigateRef.current.frameIndex;
    pendingNavigateRef.current = null;
    const clamped = Math.max(0, Math.min(episode.frame_count - 1, target));
    setFrameId(clamped);
    seekVideosToRelativeTime(frameToRelativeTime(clamped));
  }, [episode, frameToRelativeTime, seekVideosToRelativeTime]);

  const loadEpisodeTrajectories = useCallback((episodeId = selectedEpisodeId) => {
    if (episodeId == null) return;
    setLoadingTrajectories(true);
    Promise.all([
      getTrajectories(episodeId).catch(() => null),
      getFeatureSeries(episodeId, 'task_index').catch(() => ({ values: [] })),
    ])
      .then(([trajData, taskData]) => {
        if (trajData) {
          setTimestamps(trajData.timestamps || []);
          setActions(trajData.actions || []);
          setStates(trajData.states || []);
          setWarnings(trajData.warnings || []);
        }
        setTaskIndices(taskData.values || []);
        setTrajectoriesLoaded(true);
      })
      .catch((exc) => setError(exc.message))
      .finally(() => setLoadingTrajectories(false));
  }, [selectedEpisodeId]);

  useEffect(() => {
    if (selectedEpisodeId == null) return undefined;
    let cancelled = false;
    setPlaying(false);
    pauseVideos();
    setFrameId(0);
    setEpisode(null);
    setActions([]);
    setStates([]);
    setTimestamps([]);
    setTaskIndices([]);
    setTrajectoriesLoaded(false);
    setWarnings([]);
    setVideoSegments([]);
    setVideoReadyMap({});
    setVideoStalled(false);
    setEpisodeLoading(true);
    videoRefs.current = {};
    imageCacheRef.current.clear();

    getEpisode(selectedEpisodeId)
      .then((episodeData) => {
        if (cancelled) return;
        setEpisode(episodeData);
        setFps(Math.round(episodeData.fps || datasetInfo?.fps || 30));
        setError('');
        setEpisodeLoading(false);
        // Auto-load trajectories
        loadEpisodeTrajectories(selectedEpisodeId);
      })
      .catch((exc) => !cancelled && setError(exc.message));

    getEpisodeVideos(selectedEpisodeId)
      .then((data) => !cancelled && setVideoSegments(data.videos || []))
      .catch(() => !cancelled && setVideoSegments([]));

    return () => { cancelled = true; };
  }, [selectedEpisodeId, datasetInfo?.fps, pauseVideos]);

  const getSrc = useCallback((cameraName, targetFrame) => {
    if (selectedEpisodeId == null) return '';
    const frame = targetFrame != null ? targetFrame : frameIdRef.current;
    return getFrameUrl(selectedEpisodeId, frame, cameraName, JPEG_QUALITY);
  }, [selectedEpisodeId]);

  const processPreloadQueue = useCallback(() => {
    while (preloadActiveRef.current < MAX_PRELOAD_CONCURRENT && preloadQueueRef.current.length > 0) {
      const { targetFrame, cameraName } = preloadQueueRef.current.shift();
      preloadActiveRef.current += 1;
      const url = getFrameUrl(selectedEpisodeId, targetFrame, cameraName, JPEG_QUALITY);
      const img = new Image();
      img.decoding = 'async';
      img.onload = img.onerror = () => {
        preloadActiveRef.current -= 1;
        processPreloadQueue();
      };
      img.src = url;
      imageCacheRef.current.set(url, img);
    }
  }, [selectedEpisodeId]);

  const preloadFrame = useCallback((targetFrame) => {
    if (hasNativeVideos || selectedEpisodeId == null || !episode) return;
    for (const cameraName of cameraKeys) {
      const url = getFrameUrl(selectedEpisodeId, targetFrame, cameraName, JPEG_QUALITY);
      if (imageCacheRef.current.has(url)) continue;
      while (imageCacheRef.current.size > MAX_IMAGE_CACHE) {
        const oldest = imageCacheRef.current.keys().next().value;
        imageCacheRef.current.delete(oldest);
      }
      preloadQueueRef.current.push({ targetFrame, cameraName });
      processPreloadQueue();
    }
  }, [cameraKeys, episode, hasNativeVideos, selectedEpisodeId, processPreloadQueue]);

  useEffect(() => {
    if (!episode || hasNativeVideos) return;
    preloadQueueRef.current = [];
    preloadActiveRef.current = 0;
    for (let offset = 0; offset <= PRELOAD_AHEAD; offset += 1) {
      const target = frameId + offset;
      if (target < frameCount) preloadFrame(target);
    }
  }, [episode, frameId, frameCount, hasNativeVideos, preloadFrame]);

  useEffect(() => {
    if (!playing || frameCount <= 1) return undefined;
    const interval = 1000 / Math.max(1, fps);
    const tick = (time) => {
      if (hasNativeVideos) {
        let master = null;
        let masterSegment = null;
        for (const segment of videoSegments) {
          const node = videoRefs.current[segment.camera];
          if (node && node.readyState >= 2) {
            master = node;
            masterSegment = segment;
            break;
          }
        }
        if (master && masterSegment) {
          const relative = Math.max(0, master.currentTime - masterSegment.from_timestamp);
          const nextFrame = relativeTimeToFrame(relative);
          setFrameId(nextFrame);
          for (const segment of videoSegments) {
            const node = videoRefs.current[segment.camera];
            if (!node || node === master || node.readyState < 1) continue;
            const target = segment.from_timestamp + relative;
            if (Math.abs(node.currentTime - target) > SYNC_TOLERANCE_SECONDS) {
              node.currentTime = Math.min(segment.to_timestamp, Math.max(segment.from_timestamp, target));
            }
          }
          if (episodeDuration > 0 && relative >= episodeDuration) {
            pauseVideos();
            setPlaying(false);
            setFrameId(frameCount - 1);
            seekVideosToRelativeTime(episodeDuration);
            return;
          }
        }
      } else {
        if (!lastTickRef.current) lastTickRef.current = time;
        const elapsed = time - lastTickRef.current;
        if (elapsed >= interval) {
          const steps = Math.max(1, Math.floor(elapsed / interval));
          setFrameId((current) => {
            const next = current + steps;
            if (next >= frameCount - 1) {
              setPlaying(false);
              return frameCount - 1;
            }
            return next;
          });
          lastTickRef.current = time;
        }
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    if (hasNativeVideos) playVideos();
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(rafRef.current);
      lastTickRef.current = 0;
      if (hasNativeVideos) pauseVideos();
    };
  }, [episodeDuration, fps, frameCount, hasNativeVideos, pauseVideos, playVideos, playing, relativeTimeToFrame, seekVideosToRelativeTime, videoSegments]);

  const togglePlayback = useCallback(() => {
    setPlaying((value) => {
      const next = !value;
      if (!next) {
        pauseVideos();
        return false;
      }
      if (hasNativeVideos) {
        if (!allVideosReady) {
          setWarnings((prev) => {
            if (prev.some((w) => w.type === 'video_loading')) return prev;
            return [...prev, { type: 'video_loading', level: 'warning', message: '视频还未加载完，请稍候再播放' }];
          });
          return false;
        }
        if (videoStalled) {
          setWarnings((prev) => {
            if (prev.some((w) => w.type === 'video_stalled')) return prev;
            return [...prev, { type: 'video_stalled', level: 'warning', message: '部分视频缓冲区不足，播放可能卡顿' }];
          });
          return false;
        }
      }
      return true;
    });
  }, [pauseVideos, hasNativeVideos, allVideosReady, videoStalled]);

  const handleVideoReady = useCallback((camera) => {
    setVideoReadyMap((prev) => {
      const next = { ...prev, [camera]: true };
      const allReady = videoSegments.every((s) => next[s.camera]);
      if (allReady) {
        setWarnings((prev) => prev.filter((w) => w.type !== 'video_loading'));
      }
      return next;
    });
    setVideoStalled(false);
    const segment = videoByCamera.get(camera);
    const node = videoRefs.current[camera];
    if (!segment || !node) return;
    const target = segment.from_timestamp + frameToRelativeTime(frameIdRef.current);
    if (node.currentTime < segment.from_timestamp || node.currentTime > segment.to_timestamp || Math.abs(node.currentTime - target) > SYNC_TOLERANCE_SECONDS) {
      node.currentTime = Math.min(segment.to_timestamp, Math.max(segment.from_timestamp, target));
    }
  }, [frameToRelativeTime, videoByCamera]);

  const handleVideoWaiting = useCallback((camera) => {
    setVideoReadyMap((prev) => ({ ...prev, [camera]: false }));
    setVideoStalled(true);
  }, []);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement) return;
      if (event.code === 'Space') {
        event.preventDefault();
        togglePlayback();
      }
      if (event.key === 'ArrowLeft') jumpToFrame(frameId - 1);
      if (event.key === 'ArrowRight') jumpToFrame(frameId + 1);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [frameId, jumpToFrame, togglePlayback]);

  const selectedId = useMemo(() => selectedEpisodeId ?? undefined, [selectedEpisodeId]);

  const showChartsEmpty = actions.length === 0 && states.length === 0 && !loadingTrajectories;

  return (
    <div className="app-shell">
      <EpisodeList episodes={episodes} selectedId={selectedId} onSelect={setSelectedEpisodeId} />
      <main className="workspace">
        <header className="topbar">
          <div>
            <h1>lerobot-web-viz</h1>
            <p>{datasetInfo?.dataset_path || 'Use Select Folder to pick a dataset, then click Load'}</p>
          </div>
          {error && <div className="error-banner">{error}</div>}
        </header>
        <form className="dataset-loader" onSubmit={handleLoadDataset}>
          <input
            value={datasetPathInput}
            onChange={(event) => setDatasetPathInput(event.target.value)}
            placeholder="/path/to/lerobot/dataset"
          />
          <input
            value={repoIdInput}
            onChange={(event) => setRepoIdInput(event.target.value)}
            placeholder="repo id optional"
          />
          <button type="button" className="secondary-load-button" onClick={handlePickFolder}>Select Folder</button>
          <button type="submit" disabled={loadingDataset}>{loadingDataset ? 'Loading' : 'Load'}</button>
        </form>
        {episode == null ? (
          <div className="empty-state">
            {selectedEpisodeId == null ? 'Select an episode to begin' : episodeLoading ? <><span className="spinner" /> Loading episode...</> : 'Select an episode to begin'}
          </div>
        ) : (
          <>
            <MultiCameraViewer
              cameraKeys={cameraKeys}
              frameId={frameId}
              getSrc={getSrc}
              videoSegments={videoSegments}
              videoRefs={videoRefs}
              onVideoReady={handleVideoReady}
              onVideoWaiting={handleVideoWaiting}
            />
            <Timeline frameId={frameId} frameCount={frameCount} timestamp={timestamp} onChange={jumpToFrame} />
            {currentTask && <div className="current-task"><span className="task-label">Task</span> {currentTask}</div>}
            <PlayerControls
              playing={playing}
              fps={fps}
              onToggle={togglePlayback}
              onPrev={() => jumpToFrame(frameId - 1)}
              onNext={() => jumpToFrame(frameId + 1)}
              onFpsChange={setFps}
            />
            <div className="trajectory-toolbar">
              {loadingTrajectories && <span className="trajectory-status">Loading...</span>}
              {trajectoriesLoaded && !loadingTrajectories && (
                <button type="button" onClick={() => loadEpisodeTrajectories()} className="reload-button">Reload</button>
              )}
            </div>
          </>
        )}
        {showChartsEmpty ? (
          <div className="empty-state">{loadingTrajectories ? 'Loading trajectories...' : ''}</div>
        ) : (
          <>
            <TrajectoryChart
              actions={actions}
              states={states}
              actionNames={datasetInfo?.action_names}
              stateNames={datasetInfo?.state_names}
              currentFrame={frameId}
              onSelectFrame={jumpToFrame}
            />            <FeatureViewer
              episodeId={selectedEpisodeId}
              featureKeys={datasetInfo?.feature_keys}
              frameId={frameId}
              onSelectFrame={jumpToFrame}
            />
          </>
        )}
      </main>
      <DatasetInfoPanel datasetInfo={datasetInfo} episode={episode} warnings={warnings} onNavigateToFrame={navigateToFrame} />
    </div>
  );
}
