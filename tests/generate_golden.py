"""Gera o baseline da fase 0: hashes, estatísticas e miniaturas. Não versiona a imagem cheia."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from goldenlib import (
    ASSETS,
    GOLDEN_DIR,
    MODES,
    OUTPUT_PREFIX,
    ROOT,
    SCRIPT,
    environment,
    image_stats,
    load_raster,
    normalized_pdf_sha256,
    save_thumbnail,
    sha256_file,
    thumbnail_name,
    write_manifest,
)


def render_asset(source: Path, work: Path) -> None:
    prefix = work / OUTPUT_PREFIX
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(source),
            "-o",
            str(prefix),
            "--modes",
            ",".join(MODES),
            "--pdf",
        ],
        check=True,
        cwd=ROOT,
    )


def collect_output(source: Path, work: Path, kind: str, mode: str, thumb_rel: str) -> dict:
    path = work / f"{OUTPUT_PREFIX}_{mode}.{kind}"
    record = {
        "source": source.relative_to(ROOT).as_posix(),
        "mode": mode,
        "kind": kind,
        "sha256": sha256_file(path),
    }
    if kind == "pdf":
        record["sha256_normalized"] = normalized_pdf_sha256(path)
        raster = load_raster(work / f"{OUTPUT_PREFIX}_{mode}.png")
    else:
        raster = load_raster(path)
        save_thumbnail(raster, GOLDEN_DIR / thumb_rel)
        record["thumbnail"] = thumb_rel
    record.update(image_stats(raster))
    if kind == "pdf":
        record["thumbnail"] = thumb_rel
    return record


def main() -> None:
    outputs: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="better-docimage-golden-") as temporary:
        work = Path(temporary)
        for relative in ASSETS:
            source = ROOT / relative
            print(f"processando {relative}", flush=True)
            render_asset(source, work)
            for mode in MODES:
                thumb_rel = thumbnail_name(source, mode)
                for kind in ("png", "pdf"):
                    outputs.append(collect_output(source, work, kind, mode, thumb_rel))
    if len(outputs) != 18:
        raise SystemExit(f"esperadas 18 saídas, obtidas {len(outputs)}")
    write_manifest({"environment": environment(), "outputs": outputs})
    print(f"baseline gravado em {GOLDEN_DIR.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
