export default function FrameViewer({ cameraName, src, frameId }) {
  return (
    <div className="camera-tile">
      <div className="camera-label">{cameraName}</div>
      {src ? <img src={src} alt={`${cameraName} frame ${frameId}`} draggable="false" /> : <div className="empty-frame" />}
    </div>
  );
}
