const API_BASE = import.meta.env.VITE_API_BASE || '';

async function requestJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

export function getDatasetInfo() {
  return requestJson('/api/dataset/info');
}

export function getEpisodes() {
  return requestJson('/api/episodes');
}

export function getEpisode(id) {
  return requestJson(`/api/episodes/${id}`);
}

export function getFrameInfo(episodeId, frameId) {
  return requestJson(`/api/episodes/${episodeId}/frames/${frameId}`);
}

export function getFrameUrl(episodeId, frameId, cameraName, quality = 80) {
  return `${API_BASE}/api/episodes/${episodeId}/frames/${frameId}/${encodeURIComponent(cameraName)}?quality=${quality}`;
}

export function getActions(episodeId, start = 0, end = null) {
  const params = new URLSearchParams({ start });
  if (end != null) params.set('end', end);
  return requestJson(`/api/episodes/${episodeId}/actions?${params}`);
}

export function getStates(episodeId, start = 0, end = null) {
  const params = new URLSearchParams({ start });
  if (end != null) params.set('end', end);
  return requestJson(`/api/episodes/${episodeId}/states?${params}`);
}

export function getTimestamps(episodeId, start = 0, end = null) {
  const params = new URLSearchParams({ start });
  if (end != null) params.set('end', end);
  return requestJson(`/api/episodes/${episodeId}/timestamps?${params}`);
}

export function getWarnings(episodeId) {
  return requestJson(`/api/episodes/${episodeId}/warnings`);
}

export function getTrajectories(episodeId) {
  return requestJson(`/api/episodes/${episodeId}/trajectories`);
}

export async function loadDataset(datasetPath, repoId = '') {
  const response = await fetch(`${API_BASE}/api/dataset/load`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset_path: datasetPath, repo_id: repoId || null }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

export function browseServerDirectories(path = '') {
  const query = path ? `?path=${encodeURIComponent(path)}` : '';
  return requestJson(`/api/dataset/browse${query}`);
}

export async function nativePickFolder() {
  const response = await fetch(`${API_BASE}/api/dataset/pick-folder`, { method: 'POST' });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

export function scanDatasets() {
  return requestJson('/api/dataset/scan');
}

export function getEpisodeVideos(episodeId) {
  return requestJson(`/api/episodes/${episodeId}/videos`);
}

export function getAnalysis() {
  return requestJson('/api/dataset/analysis');
}

export function getFeatureSeries(episodeId, featureKey) {
  return requestJson(`/api/episodes/${episodeId}/feature/${encodeURIComponent(featureKey)}`);
}
