import SeriesChart from './SeriesChart.jsx';

export default function ActionChart({ dimNames, ...props }) {
  return <SeriesChart {...props} dimNames={dimNames} title="Action" color="#2f7dd1" />;
}
