"""Remote FLUX prompt-edit / original-camera COLMAP / Brush adapter.

Executed with the existing ComfyUI Python environment (Pillow required).
No segmentation, geometry rejection, GPU scheduling, or global Comfy interrupt.
"""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROFILE = "flux3_rgb_subject_v1"
DEFAULT_PROMPT = (
    "Edit this reference photo into a clean product documentation photograph. "
    "Keep the same subject identity, colors, material, overall shape, camera angle, "
    "perspective, framing and position. Replace the surrounding background with a "
    "plain white background and remove unrelated foreground occluders. Complete "
    "the subject surfaces behind those occluders naturally. Preserve visible fine "
    "details and the original lighting on the subject. Do not add labels, text, "
    "borders, extra objects or a different view. Local surface reconstruction is allowed."
)
# Fusion profiles are explicit; they are not claimed identical to native generate.
PRESETS = {"fast": (8000, 1200, 150000), "balanced": (15000, 1600, 300000), "high": (30000, 2000, 500000)}
IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


class Cancelled(Exception):
    pass


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def output_file(base, record):
    if record.get("type", "output") != "output":
        raise ValueError("FLUX output is not an output image")
    name, folder = record["filename"], record.get("subfolder", "")
    if Path(name).name != name or any(part == ".." for part in Path(folder).parts):
        raise ValueError("Invalid FLUX output path")
    path = (base / folder / name).resolve()
    path.relative_to(base.resolve())
    return path


def build_workflow(image, prompt, seed, prefix):
    def node(class_type, **inputs):
        return {"class_type": class_type, "inputs": inputs}

    return {
        "1": node("UNETLoader", unet_name="flux3_image_klein_sd_bf16.safetensors", weight_dtype="default"),
        "2": node("CLIPLoader", clip_name="qwen3vl_4b_bf16.safetensors", type="flux3", device="default"),
        "3": node("VAELoader", vae_name="flux2-vae.safetensors"),
        "4": node("CLIPTextEncode", text=prompt, clip=["2", 0]),
        "32": node("ConditioningZeroOut", conditioning=["4", 0]),
        "11": node("LoadImage", image=image),
        "17": node("ReferenceMultiLatent", positive=["4", 0], negative=["32", 0], vae=["3", 0], resolution="keep resolution", **{"images.image0": ["11", 0]}),
        "7": node("KSampler", model=["1", 0], positive=["17", 0], negative=["17", 1], latent_image=["17", 2], seed=seed, steps=16, cfg=1, sampler_name="euler", scheduler="simple", denoise=1),
        "8": node("VAEDecode", samples=["7", 0], vae=["3", 0]),
        "9": node("SaveImage", images=["8", 0], filename_prefix=prefix),
    }


def reference_views(originals, calibrated):
    return [(calibrated / path.name) if (calibrated / path.name).is_file() else path for path in sorted(originals.glob("*.png"))]


class Comfy:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, path, data=None):
        body = None if data is None else json.dumps(data).encode()
        request = urllib.request.Request(self.base_url + path, data=body, headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            # Keep server responses in the job's private log, never expose credentials.
            detail = error.read(8192).decode("utf-8", errors="replace")
            raise RuntimeError("ComfyUI HTTP " + str(error.code) + ": " + detail) from None

    def wait(self, prompt_id, cancelled, timeout=1200):
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            history = self.request("/history/" + prompt_id).get(prompt_id)
            if history:
                if cancelled():
                    raise Cancelled()
                if history.get("status", {}).get("status_str") == "error":
                    raise RuntimeError("FLUX inference failed; prompt_id=" + prompt_id)
                images = history.get("outputs", {}).get("9", {}).get("images", [])
                if not images:
                    raise RuntimeError("FLUX returned no image; prompt_id=" + prompt_id)
                return images[0]
            if cancelled():
                queue = self.request("/queue")
                pending = any(row[1] == prompt_id for row in queue.get("queue_pending", []))
                if pending:
                    self.request("/queue", {"delete": [prompt_id]})
                    # The prompt may have started between queue inspection and delete.
                    # Acknowledge only after its own active image is finished.
                    remaining = self.request("/queue").get("queue_running", [])
                    if not any(row[1] == prompt_id for row in remaining):
                        raise Cancelled()
                elif not any(row[1] == prompt_id for row in queue.get("queue_running", [])):
                    raise Cancelled()
                # Active prompts finish their current image. Never interrupt another job.
            time.sleep(1)
        raise TimeoutError("FLUX frame timed out; prompt_id=" + prompt_id)


def run_command(arguments, log_path, cancelled):
    if cancelled():
        raise Cancelled()
    with log_path.open("ab", buffering=0) as log:
        log.write((json.dumps(arguments) + "\n").encode())
        started = time.monotonic()
        process = subprocess.Popen(arguments, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while process.poll() is None:
                if cancelled():
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                    raise Cancelled()
                time.sleep(0.5)
            if process.returncode:
                raise RuntimeError(Path(arguments[0]).name + " failed; see " + log_path.name)
            return {"arguments": arguments, "pid": process.pid, "seconds": time.monotonic() - started, "exit_code": process.returncode}
        finally:
            process.wait()


def execute(root):
    from PIL import Image, ImageOps

    root = Path(root).resolve()
    config = read_json(root / "config.json")
    settings = config["flux3"]
    steps, resolution, max_splats = PRESETS[config["quality"]]
    work = root / "projects" / "flux3"
    work.mkdir(parents=True, exist_ok=True)
    frames, logs = work / "original_frames", work / "logs"
    frames.mkdir(exist_ok=True)
    logs.mkdir(exist_ok=True)

    def cancelled():
        return (root / "cancel.request").exists()

    receipt = {"schema_version": 1, "pipeline_profile": PROFILE, "status": "running", "quality": config["quality"], "training": {"steps": steps, "max_resolution": resolution, "max_splats": max_splats}, "commands": [], "frames": []}
    write_json(root / "pipeline_result.json", receipt)

    def stage(name, **extra):
        if cancelled():
            raise Cancelled()
        write_json(root / "status.json", {"status": "running", "stage": name, "pipeline_profile": PROFILE, **extra})
        print(json.dumps({"stage": name, **extra}), flush=True)

    def command(args, name):
        value = run_command([str(a) for a in args], logs / (name + ".log"), cancelled)
        receipt["commands"].append(value)
        write_json(root / "pipeline_result.json", receipt)
        return value

    stage("preparing_frames")
    source = root / "source"
    pictures = sorted(path for path in source.iterdir() if path.suffix.lower() in IMAGES)
    if not pictures:
        engine = Path(settings["engine_dir"])
        video = source / config["input"]
        probe = subprocess.check_output([str(engine / "ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)])
        duration = float(json.loads(probe)["format"]["duration"])
        target = {"fast": 60, "balanced": 120, "high": 150}[config["quality"]]
        extracted = work / "video_frames"
        extracted.mkdir(exist_ok=True)
        command([engine / "ffmpeg", "-y", "-i", video, "-vf", "fps=" + str(target / duration), "-frames:v", str(target), extracted / "%05d.png"], "extract")
        pictures = sorted(extracted.glob("*.png"))
    for index, path in enumerate(pictures):
        if cancelled():
            raise Cancelled()
        name = f"{index:05d}.png"
        with Image.open(path) as original:
            image = ImageOps.exif_transpose(original).convert("RGBA")
            scale = min(1, resolution / max(image.size))
            size = tuple(max(16, int(value * scale) // 16 * 16) for value in image.size)
            image = image.resize(size, Image.Resampling.LANCZOS)
            background = Image.new("RGBA", size, "white")
            background.alpha_composite(image)
            background.convert("RGB").save(frames / name)
        receipt["frames"].append({"id": name, "source": str(path.relative_to(root)), "source_sha256": digest(path), "original_sha256": digest(frames / name), "size": size, "synthetic": False})
    write_json(root / "pipeline_result.json", receipt)

    stage("original_cameras")
    engine = Path(settings["engine_dir"])
    colmap = engine / "colmap"
    geometry = work / "geometry"
    sparse = geometry / "sparse"
    sparse.mkdir(parents=True, exist_ok=True)
    database = geometry / "database.db"
    command(
        [
            colmap,
            "feature_extractor",
            "--database_path",
            database,
            "--image_path",
            frames,
            "--ImageReader.camera_model",
            "SIMPLE_RADIAL",
            "--ImageReader.single_camera",
            "1",
            "--FeatureExtraction.use_gpu",
            "0",
            "--SiftExtraction.max_image_size",
            str(resolution),
        ],
        "features",
    )
    command([colmap, "exhaustive_matcher", "--database_path", database, "--FeatureMatching.use_gpu", "0"], "matching")
    command([colmap, "mapper", "--database_path", database, "--image_path", frames, "--output_path", sparse], "cameras")
    models = sorted(path.parent for path in sparse.glob("*/images.bin"))
    if not models:
        raise RuntimeError("COLMAP did not produce camera data")
    # Native COLMAP image count (first uint64); choose the largest reconstructed model.
    import struct

    model = max(models, key=lambda path: struct.unpack("<Q", (path / "images.bin").read_bytes()[:8])[0])
    undistorted = work / "undistorted"
    command([colmap, "image_undistorter", "--image_path", frames, "--input_path", model, "--output_path", undistorted, "--output_type", "COLMAP", "--max_image_size", str(resolution)], "undistort")
    calibrated = undistorted / "images"
    original_views = reference_views(frames, calibrated)
    receipt["input_images"] = len(pictures)
    receipt["registered_images"] = len(list(calibrated.glob("*.png")))
    receipt["unregistered_frames"] = [path.name for path in original_views if path.parent == frames]
    dataset = work / "dataset"
    (dataset / "images").mkdir(parents=True, exist_ok=True)
    camera_source = undistorted / "sparse"
    if not (camera_source / "cameras.bin").is_file():
        camera_source = camera_source / "0"
    shutil.copytree(camera_source, dataset / "sparse" / "0", dirs_exist_ok=True)
    receipt["cameras"] = {name: digest(dataset / "sparse" / "0" / name) for name in ["cameras.bin", "images.bin", "points3D.bin"]}

    comfy = Comfy(settings["base_url"])
    data = Path(settings["deploy_root"]) / "data"
    relative_input = Path("xingxi") / root.name
    input_dir = data / "input" / relative_input
    input_dir.mkdir(parents=True, exist_ok=True)
    edits = work / "flux_edits"
    edits.mkdir(exist_ok=True)
    total = len(original_views)
    for index, image in enumerate(original_views):
        stage("preprocessing", preprocess_progress={"completed": index, "total": total})
        shutil.copy2(image, input_dir / image.name)
        graph = build_workflow((relative_input / image.name).as_posix(), config["preprocess_prompt"], config["preprocess_seed"], "xingxi/" + root.name + "/" + image.stem)
        graph_path = edits / (image.stem + "-workflow.json")
        write_json(graph_path, graph)
        state_path = edits / (image.stem + "-receipt.json")
        frame = read_json(state_path)
        if not frame.get("prompt_id"):
            submission = comfy.request("/prompt", {"prompt": graph, "client_id": root.name})
            frame = {"prompt_id": submission["prompt_id"], "original_sha256": digest(image), "workflow_sha256": digest(graph_path), "seed": config["preprocess_seed"], "synthetic": True}
            write_json(state_path, frame)
        record = comfy.wait(frame["prompt_id"], cancelled)
        output = output_file(data / "output", record)
        shutil.copy2(output, edits / image.name)
        with Image.open(image) as original, Image.open(output) as generated:
            # Deterministic full-frame resize; no crop, structural gate, or alpha extraction.
            generated.convert("RGB").resize(original.size, Image.Resampling.LANCZOS).save(dataset / "images" / image.name)
        frame.update(output=record, edited_sha256=digest(dataset / "images" / image.name), name=image.name)
        write_json(state_path, frame)
    stage("preprocessing", preprocess_progress={"completed": total, "total": total})
    receipt["flux"] = {
        "prompt": config["preprocess_prompt"],
        "seed": config["preprocess_seed"],
        "steps": 16,
        "cfg": 1,
        "sampler": "euler",
        "scheduler": "simple",
        "resolution": "keep resolution",
        "processed_images": total,
        "receipts": [str(p.relative_to(root)) for p in sorted(edits.glob("*-receipt.json"))],
    }
    write_json(root / "pipeline_result.json", receipt)
    stage("training", preprocess_progress={"completed": total, "total": total})
    args = [engine / "brush_app", dataset, "--total-steps", str(steps), "--max-resolution", str(resolution), "--max-splats", str(max_splats), "--export-every", str(steps), "--export-path", work, "--export-name", "final.ply"]
    if config["quality"] == "high":
        args += ["--growth-grad-threshold", "0.00003", "--growth-select-fraction", "0.25", "--growth-stop-iter", "25000"]
    command(args, "brush")
    result = work / "final.ply"
    receipt.update(status="completed", output={"finalPly": str(result), "sha256": digest(result), "size": result.stat().st_size})
    write_json(root / "pipeline_result.json", receipt)


if __name__ == "__main__":
    try:
        execute(sys.argv[1])
    except Cancelled:
        sys.exit(130)
