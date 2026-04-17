from fastapi import HTTPException, Response
from fastapi.responses import FileResponse


def register_study_http_routes(app, *, study_dir, safe_study_path):
    @app.get("/study/catalog")
    async def study_catalog():
        if not study_dir.exists():
            return {"folders": []}
        folders = []
        for folder in sorted([p for p in study_dir.iterdir() if p.is_dir()]):
            files = []
            for f in sorted(folder.glob("*.pdf")):
                name = f.name
                is_answer_key = "answer key" in name.lower()
                rel = f.relative_to(study_dir).as_posix()
                files.append({
                    "name": name,
                    "path": rel,
                    "is_answer_key": is_answer_key,
                })
            if files:
                folders.append({"name": folder.name, "files": files})
        return {"folders": folders}

    @app.get("/study/file")
    async def study_file(path: str):
        safe_path = safe_study_path(path)
        if not safe_path.exists() or safe_path.suffix.lower() != ".pdf":
            raise HTTPException(status_code=404, detail="File not found")
        if "answer key" in safe_path.name.lower():
            raise HTTPException(status_code=403, detail="Answer key is restricted")
        headers = {
            "Content-Disposition": f'inline; filename="{safe_path.name}"',
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Type, Authorization",
            "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
        }
        return FileResponse(
            str(safe_path),
            media_type="application/pdf",
            headers=headers,
        )

    @app.options("/study/file")
    async def study_file_options():
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Range, Content-Type, Authorization",
                "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
            },
        )
