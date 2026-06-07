import { useMemo } from 'react';
import FrameViewer from './FrameViewer.jsx';

export default function MultiCameraViewer({ cameraKeys, frameId, getSrc, videoSegments, videoRefs, onVideoReady, onVideoWaiting }) {
  const segmentByCamera = useMemo(
    () => new Map((videoSegments || []).map((segment) => [segment.camera, segment])),
    [videoSegments]
  );

  return (
    <section className="viewer-grid">
      {cameraKeys.map((camera) => {
        const segment = segmentByCamera.get(camera);
        if (!segment) {
          return <FrameViewer key={camera} cameraName={camera} frameId={frameId} src={getSrc(camera)} />;
        }
        return (
          <div className="camera-tile" key={camera}>
            <div className="camera-label">{camera}</div>
            <video
              ref={(node) => {
                if (node) videoRefs.current[camera] = node;
                else delete videoRefs.current[camera];
              }}
              src={segment.url}
              muted
              playsInline
              preload="auto"
              onCanPlayThrough={() => onVideoReady(camera)}
              onWaiting={() => onVideoWaiting && onVideoWaiting(camera)}
              onStalled={() => onVideoWaiting && onVideoWaiting(camera)}
            />
          </div>
        );
      })}
    </section>
  );
}
