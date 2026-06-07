import SeriesChart from './SeriesChart.jsx';

export default function StateChart({ dimNames, ...props }) {
  return <SeriesChart {...props} dimNames={dimNames} title="State" color="#0f766e" />;
}
