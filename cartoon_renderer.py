import argparse
import math
from pathlib import Path

import cv2
import numpy as np


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
STYLE_PRESETS = {"basic", "soft", "vivid", "cinematic"}


def quantize_colors_kmeans(image: np.ndarray, k: int, attempts: int = 3) -> np.ndarray:
    data = image.reshape((-1, 3)).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, labels, centers = cv2.kmeans(
        data,
        k,
        None,
        criteria,
        attempts,
        cv2.KMEANS_PP_CENTERS,
    )
    centers = np.uint8(centers)
    quantized = centers[labels.flatten()].reshape(image.shape)
    return quantized


def build_edge_mask(gray: np.ndarray, block_size: int, c_value: int, blur_ksize: int) -> np.ndarray:
    if blur_ksize % 2 == 0:
        blur_ksize += 1
    if block_size % 2 == 0:
        block_size += 1
    if block_size < 3:
        block_size = 3

    smoothed = cv2.medianBlur(gray, blur_ksize)
    edges = cv2.adaptiveThreshold(
        smoothed,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY,
        block_size,
        c_value,
    )
    return edges


def cartoonize(
    image: np.ndarray,
    k_colors: int,
    bilateral_d: int,
    bilateral_sigma_color: int,
    bilateral_sigma_space: int,
    edge_block_size: int,
    edge_c_value: int,
    edge_blur_ksize: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    # Bilateral filtering preserves edges while flattening texture.
    smooth = cv2.bilateralFilter(image, bilateral_d, bilateral_sigma_color, bilateral_sigma_space)
    quantized = quantize_colors_kmeans(smooth, k=k_colors)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edge_mask = build_edge_mask(gray, edge_block_size, edge_c_value, edge_blur_ksize)

    # Return quantized directly without edge mask for smoother cartoon style
    cartoon = quantized
    return cartoon, quantized, edge_mask


def apply_style_preset(image: np.ndarray, style: str) -> np.ndarray:
    if style == "basic":
        return image

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)

    if style == "soft":
        hsv[:, :, 1] *= 0.9
        hsv[:, :, 2] *= 1.05
        hsv = np.clip(hsv, 0, 255).astype(np.uint8)
        styled = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        return cv2.GaussianBlur(styled, (3, 3), 0)

    if style == "vivid":
        hsv[:, :, 1] *= 1.25
        hsv[:, :, 2] *= 1.05
        hsv = np.clip(hsv, 0, 255).astype(np.uint8)
        return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    # cinematic: slightly lower saturation, stronger local contrast
    hsv[:, :, 1] *= 0.82
    hsv[:, :, 2] *= 0.98
    hsv = np.clip(hsv, 0, 255).astype(np.uint8)
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def get_effective_params(args: argparse.Namespace) -> tuple[int, int, int, int]:
    if args.style == "soft":
        return max(4, min(args.k_colors, 8)), max(args.bilateral_d, 11), max(args.bilateral_sigma_color, 140), max(args.bilateral_sigma_space, 140)
    if args.style == "vivid":
        return max(args.k_colors, 10), max(args.bilateral_d, 9), max(args.bilateral_sigma_color, 110), max(args.bilateral_sigma_space, 110)
    if args.style == "cinematic":
        return max(5, min(args.k_colors, 9)), max(args.bilateral_d, 11), max(args.bilateral_sigma_color, 150), max(args.bilateral_sigma_space, 150)
    return args.k_colors, args.bilateral_d, args.bilateral_sigma_color, args.bilateral_sigma_space


def adjust_params_by_strength(k_colors: int, bilateral_d: int, sigma_color: int, sigma_space: int, strength: float) -> tuple[int, int, int, int]:
    strength = float(np.clip(strength, 0.0, 1.0))

    # Higher strength means fewer colors and stronger smoothing.
    k_scale = 1.25 - 0.75 * strength
    smooth_scale = 0.8 + 0.85 * strength

    k_adj = int(round(k_colors * k_scale))
    d_adj = int(round(bilateral_d * smooth_scale))
    sigma_color_adj = int(round(sigma_color * smooth_scale))
    sigma_space_adj = int(round(sigma_space * smooth_scale))

    return max(2, k_adj), max(1, d_adj), max(1, sigma_color_adj), max(1, sigma_space_adj)


def blend_by_strength(original: np.ndarray, cartoon: np.ndarray, strength: float) -> np.ndarray:
    strength = float(np.clip(strength, 0.0, 1.0))
    return cv2.addWeighted(cartoon, strength, original, 1.0 - strength, 0.0)


def get_face_cascade() -> cv2.CascadeClassifier | None:
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    if not cascade_path.exists():
        return None

    cascade = cv2.CascadeClassifier(str(cascade_path))
    if cascade.empty():
        return None
    return cascade


def enhance_faces(cartoon: np.ndarray, original: np.ndarray, strength: float) -> tuple[np.ndarray, int]:
    cascade = get_face_cascade()
    if cascade is None:
        return cartoon, 0

    gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(36, 36))
    if len(faces) == 0:
        return cartoon, 0

    strength = float(np.clip(strength, 0.0, 1.0))
    enhanced = cartoon.copy()

    for x, y, w, h in faces:
        roi_c = enhanced[y : y + h, x : x + w]
        roi_o = original[y : y + h, x : x + w]
        if roi_c.size == 0 or roi_o.size == 0:
            continue

        # Gentle denoise + slight tone lift inside face region.
        smooth = cv2.bilateralFilter(roi_c, 7, 45, 45)
        hsv = cv2.cvtColor(smooth, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 1] *= 1.0 + 0.12 * strength
        hsv[:, :, 2] *= 1.0 + 0.10 * strength
        tuned = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)

        skin_preserved = cv2.addWeighted(tuned, 0.78, roi_o, 0.22, 0.0)
        roi_final = cv2.addWeighted(roi_c, 1.0 - strength, skin_preserved, strength, 0.0)
        enhanced[y : y + h, x : x + w] = roi_final

    return enhanced, int(len(faces))


def render_variant_sheet(original: np.ndarray, variants: list[tuple[str, np.ndarray]], output_path: Path) -> None:
    tiles = [("original", original)] + variants
    if not tiles:
        return

    cols = 3
    rows = int(math.ceil(len(tiles) / cols))
    thumb_w = 320

    h, w = original.shape[:2]
    scale = thumb_w / float(w)
    thumb_h = max(1, int(h * scale))
    label_h = 34

    canvas = np.full((rows * (thumb_h + label_h), cols * thumb_w, 3), 248, dtype=np.uint8)

    for idx, (name, image) in enumerate(tiles):
        r = idx // cols
        c = idx % cols
        x0 = c * thumb_w
        y0 = r * (thumb_h + label_h)

        resized = cv2.resize(image, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
        canvas[y0 + label_h : y0 + label_h + thumb_h, x0 : x0 + thumb_w] = resized
        cv2.putText(canvas, name, (x0 + 10, y0 + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (25, 25, 25), 1, cv2.LINE_AA)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), canvas)


def score_candidate(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    contrast_score = float(np.std(gray))
    sat_mean = float(np.mean(hsv[:, :, 1]))
    sat_score = 255.0 - abs(sat_mean - 120.0)
    edge_energy = float(cv2.Laplacian(gray, cv2.CV_32F).var())

    return 0.45 * contrast_score + 0.25 * sat_score + 0.30 * min(edge_energy, 300.0)


def run_cartoon_pipeline(image: np.ndarray, args: argparse.Namespace, style: str, strength: float, apply_face_enhance: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    base_k, base_d, base_sigma_color, base_sigma_space = get_effective_params(args)
    if style != args.style:
        temp_args = argparse.Namespace(**vars(args))
        temp_args.style = style
        base_k, base_d, base_sigma_color, base_sigma_space = get_effective_params(temp_args)

    k_adj, d_adj, sigma_color_adj, sigma_space_adj = adjust_params_by_strength(base_k, base_d, base_sigma_color, base_sigma_space, strength)

    cartoon, quantized, edges = cartoonize(
        image=image,
        k_colors=k_adj,
        bilateral_d=d_adj,
        bilateral_sigma_color=sigma_color_adj,
        bilateral_sigma_space=sigma_space_adj,
        edge_block_size=max(3, args.edge_block_size),
        edge_c_value=args.edge_c_value,
        edge_blur_ksize=max(1, args.edge_blur_ksize),
    )

    cartoon = apply_style_preset(cartoon, style)
    cartoon = blend_by_strength(image, cartoon, strength)

    face_count = 0
    if apply_face_enhance:
        cartoon, face_count = enhance_faces(cartoon, image, args.face_enhance_strength)

    return cartoon, quantized, edges, face_count


def run_auto_search(image: np.ndarray, args: argparse.Namespace, stem: str, output_dir: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, str, float, int]:
    candidates = [
        ("soft_45", "soft", 0.45),
        ("soft_70", "soft", 0.70),
        ("vivid_60", "vivid", 0.60),
        ("vivid_88", "vivid", 0.88),
        ("cinematic_65", "cinematic", 0.65),
        ("cinematic_88", "cinematic", 0.88),
    ]

    scored = []
    variants_for_sheet = []
    for name, style, strength in candidates:
        cartoon, quantized, edges, face_count = run_cartoon_pipeline(
            image=image,
            args=args,
            style=style,
            strength=strength,
            apply_face_enhance=args.face_enhance,
        )
        score = score_candidate(cartoon)

        candidate_path = output_dir / f"{stem}_candidate_{name}.png"
        cv2.imwrite(str(candidate_path), cartoon)

        scored.append((score, name, style, strength, cartoon, quantized, edges, face_count))
        variants_for_sheet.append((f"{style} {strength:.2f}", cartoon))

    render_variant_sheet(image, variants_for_sheet, output_dir / f"{stem}_search_sheet.png")

    scored.sort(key=lambda item: item[0], reverse=True)
    _, _, best_style, best_strength, best_cartoon, best_quantized, best_edges, best_face_count = scored[0]
    return best_cartoon, best_quantized, best_edges, best_style, best_strength, best_face_count


def create_contact_sheet(pairs: list[tuple[Path, Path]], output_path: Path, thumb_width: int = 320) -> None:
    if not pairs:
        return

    rows = []
    for src_path, out_path in pairs:
        src = cv2.imread(str(src_path))
        out = cv2.imread(str(out_path))
        if src is None or out is None:
            continue

        h, w = src.shape[:2]
        ratio = thumb_width / float(w)
        thumb_height = max(1, int(h * ratio))

        src_t = cv2.resize(src, (thumb_width, thumb_height), interpolation=cv2.INTER_AREA)
        out_t = cv2.resize(out, (thumb_width, thumb_height), interpolation=cv2.INTER_AREA)
        row = np.hstack([src_t, out_t])

        label_h = 34
        labeled = np.full((thumb_height + label_h, row.shape[1], 3), 245, dtype=np.uint8)
        labeled[label_h:, :, :] = row
        cv2.putText(labeled, f"Input: {src_path.name}", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (30, 30, 30), 1, cv2.LINE_AA)
        cv2.putText(labeled, "Output", (thumb_width + 10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (30, 30, 30), 1, cv2.LINE_AA)

        rows.append(labeled)

    if not rows:
        return

    contact_sheet = np.vstack(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), contact_sheet)


def save_intermediate_outputs(output_path: Path, quantized: np.ndarray, edges: np.ndarray) -> None:
    stem = output_path.stem
    parent = output_path.parent
    quant_path = parent / f"{stem}_quantized.png"
    edge_path = parent / f"{stem}_edges.png"

    cv2.imwrite(str(quant_path), quantized)
    cv2.imwrite(str(edge_path), edges)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cartoon rendering using OpenCV image processing")
    parser.add_argument("--input", default="input", help="Path to input image or folder (default: input)")
    parser.add_argument("--output", default="", help="Path to save output image (single-image mode only)")
    parser.add_argument("--output-dir", default="outputs", help="Directory to save output images")
    parser.add_argument("--k-colors", type=int, default=8, help="Number of color clusters for k-means")
    parser.add_argument("--bilateral-d", type=int, default=9, help="Diameter of bilateral filter")
    parser.add_argument("--bilateral-sigma-color", type=int, default=120, help="Color sigma for bilateral filter")
    parser.add_argument("--bilateral-sigma-space", type=int, default=120, help="Space sigma for bilateral filter")
    parser.add_argument("--edge-block-size", type=int, default=9, help="Adaptive threshold block size")
    parser.add_argument("--edge-c-value", type=int, default=7, help="Adaptive threshold C value")
    parser.add_argument("--edge-blur-ksize", type=int, default=5, help="Median blur kernel size for edge map")
    parser.add_argument("--style", default="basic", choices=sorted(STYLE_PRESETS), help="Cartoon style preset")
    parser.add_argument("--cartoon-strength", type=float, default=0.7, help="Cartoon intensity from 0.0 (weak) to 1.0 (strong)")
    parser.add_argument("--face-enhance", action="store_true", help="Enhance facial regions for portrait photos")
    parser.add_argument("--face-enhance-strength", type=float, default=0.55, help="Face enhancement strength from 0.0 to 1.0")
    parser.add_argument("--auto-search", action="store_true", help="Generate multiple style/parameter candidates and auto-pick one")
    parser.add_argument("--contact-sheet", action="store_true", help="Save one summary image for batch results")
    parser.add_argument("--show", action="store_true", help="Show original and cartoonized images")
    parser.add_argument("--save-steps", action="store_true", help="Save intermediate images (quantized and edges)")
    parser.add_argument("--compare", action="store_true", help="Save side-by-side comparison image")
    return parser.parse_args()


def collect_input_images(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]

    files = []
    for path in sorted(input_path.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)
    return files


def process_single_image(image_path: Path, output_path: Path, args: argparse.Namespace) -> None:
    image = cv2.imread(str(image_path))
    if image is None:
        print(f"[WARN] Failed to read image: {image_path}")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cartoon_strength = float(np.clip(args.cartoon_strength, 0.0, 1.0))
    face_strength = float(np.clip(args.face_enhance_strength, 0.0, 1.0))
    args.face_enhance_strength = face_strength

    if args.auto_search:
        cartoon, quantized, edges, used_style, used_strength, face_count = run_auto_search(
            image=image,
            args=args,
            stem=output_path.stem,
            output_dir=output_path.parent,
        )
    else:
        cartoon, quantized, edges, face_count = run_cartoon_pipeline(
            image=image,
            args=args,
            style=args.style,
            strength=cartoon_strength,
            apply_face_enhance=args.face_enhance,
        )
        used_style = args.style
        used_strength = cartoon_strength

    ok = cv2.imwrite(str(output_path), cartoon)
    if not ok:
        print(f"[WARN] Failed to save output image: {output_path}")
        return

    if args.save_steps:
        save_intermediate_outputs(output_path, quantized, edges)

    if args.compare:
        comparison = np.hstack([image, cartoon])
        compare_path = output_path.parent / f"{output_path.stem}_compare.png"
        cv2.imwrite(str(compare_path), comparison)

    print(f"[INFO] Input:  {image_path}")
    print(f"[INFO] Output: {output_path}")
    print(f"[INFO] Style:  {used_style}")
    print(f"[INFO] Strength: {used_strength:.2f}")
    if args.face_enhance:
        print(f"[INFO] Face enhance: ON (faces detected: {face_count})")
    if args.auto_search:
        print(f"[INFO] Auto-search sheet: {output_path.parent / (output_path.stem + '_search_sheet.png')}")

    if args.show:
        cv2.imshow("Original", image)
        cv2.imshow("Cartoon", cartoon)
        cv2.waitKey(0)


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    if not input_path.exists():
        if args.input == "input":
            input_path.mkdir(parents=True, exist_ok=True)
            print(f"[INFO] Created input folder: {input_path.resolve()}")
            print("[INFO] Put images in the input folder and run again.")
            return
        raise FileNotFoundError(f"Input path not found: {input_path}")

    images = collect_input_images(input_path)
    if not images:
        print(f"[INFO] No supported images found in: {input_path}")
        print(f"[INFO] Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    processed_pairs = []

    for image_path in images:
        if input_path.is_file() and args.output:
            output_path = Path(args.output)
        else:
            output_path = output_dir / f"{image_path.stem}_cartoon.png"

        process_single_image(image_path, output_path, args)
        processed_pairs.append((image_path, output_path))

    if args.contact_sheet and len(processed_pairs) > 1:
        sheet_path = output_dir / "contact_sheet.png"
        create_contact_sheet(processed_pairs, sheet_path)
        print(f"[INFO] Contact sheet: {sheet_path}")

    print(f"[INFO] Cartoon rendering completed ({len(images)} image(s))")

    if args.show:
        cv2.destroyAllWindows()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
