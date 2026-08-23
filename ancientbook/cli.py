# -*- coding: utf-8 -*-
"""CLI: ancientbook ingest / ocr / structure / export / review / run."""
from __future__ import annotations

from pathlib import Path

import click

from ancientbook.config import PipelineConfig, ensure_dirs
from ancientbook.ingest import safe_book_name
from ancientbook.manifest import get_manifest
from ancientbook.pipeline import run_export, run_ingest, run_ocr
from ancientbook.review import generate_review_queue


pass_config = click.make_pass_decorator(PipelineConfig)


@click.group()
@click.option("--root", type=click.Path(path_type=Path), default=None,
              help="项目根目录，默认 ~/Documents/AncientBooks")
@click.option("--dpi", type=int, default=None)
@click.option("--ocr-quality", type=click.Choice(["v5", "high", "mobile"]), default=None)
@click.option("--high-priority-threshold", type=float, default=None)
@click.option("--review-threshold", type=float, default=None)
@click.option("--commentary-height-ratio", type=float, default=None)
@click.option("--preprocess/--no-preprocess", default=None, help="OCR 前背景平坦化（默认开）")
@click.pass_context
def main(ctx, root, dpi, ocr_quality, high_priority_threshold, review_threshold, commentary_height_ratio, preprocess):
    """AncientBooks PDF -> Obsidian Knowledge Pipeline CLI."""
    cfg = PipelineConfig()
    if root:
        cfg.project_root = root
    if dpi is not None:
        cfg.dpi = dpi
    if ocr_quality is not None:
        cfg.ocr_quality = ocr_quality
    if high_priority_threshold is not None:
        cfg.high_priority_threshold = high_priority_threshold
    if review_threshold is not None:
        cfg.review_threshold = review_threshold
    if commentary_height_ratio is not None:
        cfg.commentary_height_ratio = commentary_height_ratio
    if preprocess is not None:
        cfg.preprocess = preprocess
    ensure_dirs()
    ctx.obj = cfg


@main.command()
@click.argument("pdf", type=click.Path(exists=True, path_type=Path))
@click.option("--book", required=True, help="书名（用于目录与 manifest）")
@click.option("--volume", default="卷一", help="卷名")
@click.option("--limit-pages", type=int, default=0, help="仅处理前 N 页 PDF")
@pass_config
def ingest(config, pdf, book, volume, limit_pages):
    """PDF 转页面/叶图像并记录 manifest。"""
    manifest = get_manifest(config)
    leaves = run_ingest(pdf, book, volume, config, limit_pages, manifest=manifest)
    click.echo(f"[ingest] 生成 {len(leaves)} 叶图像，manifest 已更新。")
    for leaf in leaves[:5]:
        click.echo(f"  - {leaf.side} leaf {leaf.leaf_number}: {leaf.image_path}")


@main.command()
@click.option("--book", required=True, help="书名")
@click.option("--limit-leaves", type=int, default=0, help="仅 OCR 前 N 叶")
@click.option("--force", is_flag=True, help="忽略缓存重新 OCR")
@pass_config
def ocr(config, book, limit_leaves, force):
    """对已经 ingest 的叶图像执行 OCR（Raw + Structured JSON）。"""
    manifest = get_manifest(config)
    img_dir = config.dir("sources_images") / safe_book_name(book)
    if not img_dir.exists():
        raise click.ClickException(f"未找到图像目录: {img_dir}，请先运行 ingest。")
    # collect leaves from manifest for this book
    recs = [r for r in manifest.all().values() if r.book == book]
    recs.sort(key=lambda r: (r.pdf_page, 0 if r.side == "R" else 1))
    if limit_leaves:
        recs = recs[:limit_leaves]

    # materialize Leaf objects
    from ancientbook.models import Leaf
    processed = 0
    skipped = 0
    for rec in recs:
        leaf = Leaf(
            book=rec.book,
            pdf_path=Path(rec.pdf_path),
            pdf_index=rec.pdf_page - 1,
            side=rec.side,
            leaf_number=rec.leaf,
            image_path=Path(rec.image_file),
            image_hash=rec.image_hash,
        )
        t = run_ocr(leaf, config, manifest, force=force)
        if t is None:
            skipped += 1
            click.echo(f"[ocr] {book} leaf {rec.leaf} {rec.side}: SKIP (up to date)")
        else:
            processed += 1
            click.echo(f"[ocr] {book} leaf {rec.leaf} {rec.side}: OK conf={t.ocr_confidence:.3f}")
    click.echo(f"[ocr] 完成：处理 {processed} / 跳过 {skipped}")


def _leaf_from_record(rec):
    from ancientbook.models import Leaf
    return Leaf(
        book=rec.book,
        pdf_path=Path(rec.pdf_path),
        pdf_index=rec.pdf_page - 1,
        side=rec.side,
        leaf_number=rec.leaf,
        image_path=Path(rec.image_file),
        image_hash=rec.image_hash,
    )


@main.command()
@click.option("--book", required=True, help="书名")
@pass_config
def export(config, book):
    """将 structured OCR 转写为 canonical Markdown。"""
    manifest = get_manifest(config)
    recs = [r for r in manifest.all().values() if r.book == book and r.structured_ocr_path]
    exported = 0
    for rec in recs:
        leaf = _leaf_from_record(rec)
        t = run_ocr(leaf, config, manifest, force=False)
        if t is None:
            click.echo(f"[export] {book} leaf {rec.leaf} {rec.side}: no structured data")
            continue
        run_export(t, config, manifest)
        exported += 1
    click.echo(f"[export] 完成 {exported} 叶 Markdown 导出。")


@main.command()
@click.argument("pdf", type=click.Path(exists=True, path_type=Path))
@click.option("--book", required=True, help="书名（用于目录与 manifest）")
@click.option("--volume", default="卷一", help="卷名")
@click.option("--limit-pages", type=int, default=0, help="仅处理前 N 页 PDF")
@click.option("--limit-leaves", type=int, default=0, help="仅 OCR 前 N 叶")
@click.option("--force", is_flag=True, help="忽略缓存重新 OCR")
@click.option("--review/--no-review", default=True, help="是否生成 review_queue.md")
@pass_config
def run(config, pdf, book, volume, limit_pages, limit_leaves, force, review):
    """一键跑完 ingest → ocr → export → review。"""
    manifest = get_manifest(config)
    click.echo(f"[run] book={book} volume={volume} quality={config.ocr_quality} dpi={config.dpi}")

    leaves = run_ingest(pdf, book, volume, config, limit_pages, manifest=manifest)
    if limit_leaves:
        leaves = leaves[:limit_leaves]

    processed = 0
    for leaf in leaves:
        t = run_ocr(leaf, config, manifest, force=force)
        if t:
            run_export(t, config, manifest)
            processed += 1
            click.echo(f"[run] leaf {leaf.leaf_number} {leaf.side}: conf={t.ocr_confidence:.3f}")

    if review:
        path = generate_review_queue(manifest, config)
        click.echo(f"[run] review queue: {path}")

    click.echo(f"[run] 完成：ingested {len(leaves)} leaves, exported {processed}.")


@main.command(name="review")
@pass_config
def review_cmd(config):
    """生成 OCR Review Queue。"""
    manifest = get_manifest(config)
    path = generate_review_queue(manifest, config)
    click.echo(f"[review] 已生成: {path}")


@main.command()
@pass_config
def status(config):
    """查看 manifest 汇总。"""
    manifest = get_manifest(config)
    records = list(manifest.all().values())
    click.echo(f"Manifest: {len(records)} records")
    by_book = {}
    for r in records:
        by_book.setdefault(r.book, {"total": 0, "ocr": 0, "md": 0})
        by_book[r.book]["total"] += 1
        if r.raw_ocr_path:
            by_book[r.book]["ocr"] += 1
        if r.markdown_path:
            by_book[r.book]["md"] += 1
    for b, s in by_book.items():
        click.echo(f"  {b}: {s['total']} leaves, OCR {s['ocr']}, MD {s['md']}")


if __name__ == "__main__":
    main()
