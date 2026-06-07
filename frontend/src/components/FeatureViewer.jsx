import { useState } from 'react';
import { getFeatureSeries } from '../api/client.js';
import SeriesChart from './SeriesChart.jsx';

export default function FeatureViewer({ episodeId, featureKeys, frameId, onSelectFrame }) {
  const [selectedFeature, setSelectedFeature] = useState('');
  const [values, setValues] = useState([]);
  const [selectedDim, setSelectedDim] = useState(0);
  const [loading, setLoading] = useState(false);

  function handleSelectFeature(key) {
    setSelectedFeature(key);
    if (!key || episodeId == null) {
      setValues([]);
      return;
    }
    setLoading(true);
    getFeatureSeries(episodeId, key)
      .then((data) => setValues(data.values || []))
      .catch(() => setValues([]))
      .finally(() => setLoading(false));
  }

  if (!featureKeys || featureKeys.length === 0) return null;

  return (
    <div className="feature-viewer">
      <div className="chart-header">
        <div className="panel-title">Feature</div>
        <select
          value={selectedFeature}
          onChange={(e) => handleSelectFeature(e.target.value)}
        >
          <option value="">-- select feature --</option>
          {featureKeys.map((key) => (
            <option key={key} value={key}>{key}</option>
          ))}
        </select>
        {loading && <span className="loading-hint">loading...</span>}
      </div>
      {selectedFeature && values.length > 0 && (
        <SeriesChart
          title={selectedFeature}
          values={values}
          currentFrame={frameId}
          selectedDim={selectedDim}
          onDimChange={setSelectedDim}
          onSelectFrame={onSelectFrame}
          color="#d97706"
        />
      )}
    </div>
  );
}
