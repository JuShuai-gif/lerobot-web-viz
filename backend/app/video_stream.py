from fastapi import Response


def jpeg_response(content: bytes, cache_seconds: int = 60) -> Response:
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={
            "Cache-Control": f"public, max-age={cache_seconds}",
            "Content-Length": str(len(content)),
        },
    )
