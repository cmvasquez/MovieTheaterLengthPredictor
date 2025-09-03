import os
import pathlib
import zipfile


def zip_release(version: str) -> str:
    root = pathlib.Path(__file__).resolve().parents[1]
    dist_dir = root / "dist" / "MovieTheaterLengthPredictor"
    out_dir = root / "release"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"MovieTheaterLengthPredictor-{version}.zip"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in dist_dir.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(dist_dir).as_posix())
    return str(zip_path)


if __name__ == "__main__":
    version = os.environ.get("APP_VERSION", "v0.0.2")
    out = zip_release(version)
    print(f"Zipped to {out}")
