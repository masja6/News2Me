"""FastAPI admin UI. http://localhost:8000/"""
import uvicorn

from newstome.ui import app


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
