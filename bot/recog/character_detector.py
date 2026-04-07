import pickle
import cv2
import numpy as np
from pathlib import Path

TEMPLATE_DIR = Path("resource/umamusume/trainingIcons")
BAKED_PATH = Path("resource/umamusume/trainingIcons.pkl")


def has_portrait_circle(roi, circle_cx, circle_cy, circle_r):
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 40, 100)
    h, w = edges.shape
    ring_outer = np.zeros((h, w), dtype=np.uint8)
    ring_inner = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(ring_outer, (circle_cx, circle_cy), circle_r + 4, 255, -1)
    cv2.circle(ring_inner, (circle_cx, circle_cy), circle_r - 4, 255, -1)
    ring_mask = cv2.subtract(ring_outer, ring_inner)
    ring_edges = cv2.bitwise_and(edges, ring_mask)
    ring_area = np.sum(ring_mask > 0)
    ring_edge_count = np.sum(ring_edges > 0)
    edge_ratio = ring_edge_count / max(ring_area, 1)
    if edge_ratio <= 0.15:
        return False
    inner_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(inner_mask, (circle_cx, circle_cy), circle_r - 8, 255, -1)
    inner_edges = cv2.bitwise_and(edges, inner_mask)
    inner_edge_ratio = np.sum(inner_edges > 0) / max(np.sum(inner_mask > 0), 1)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    inner_sat = hsv[:, :, 1][inner_mask > 0]
    inner_hue = hsv[:, :, 0][inner_mask > 0]
    sat_std = np.std(inner_sat) if len(inner_sat) > 0 else 0
    hue_std = np.std(inner_hue) if len(inner_hue) > 0 else 0
    has_content = inner_edge_ratio > 0.08 or sat_std > 25
    has_diverse_hue = hue_std > 25
    return has_content and has_diverse_hue


def extract_circle_from_roi(roi, circle_cx, circle_cy, circle_r):
    x1 = max(0, circle_cx - circle_r)
    y1 = max(0, circle_cy - circle_r)
    x2 = min(roi.shape[1], circle_cx + circle_r)
    y2 = min(roi.shape[0], circle_cy + circle_r)
    return cv2.resize(roi[y1:y2, x1:x2], (92, 92), interpolation=cv2.INTER_AREA)


def compute_features(img_bgr):
    sz = img_bgr.shape[0]
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    features = []
    mask_full = np.zeros((sz, sz), dtype=np.uint8)
    cv2.circle(mask_full, (sz // 2, sz // 2), sz // 2 - 8, 255, -1)
    mask_hair = np.zeros((sz, sz), dtype=np.uint8)
    mask_hair[:int(sz * 0.35), :] = mask_full[:int(sz * 0.35), :]
    mask_face = np.zeros((sz, sz), dtype=np.uint8)
    mask_face[int(sz * 0.30):int(sz * 0.65), :] = mask_full[int(sz * 0.30):int(sz * 0.65), :]
    mask_body = np.zeros((sz, sz), dtype=np.uint8)
    mask_body[int(sz * 0.65):, :] = mask_full[int(sz * 0.65):, :]
    half = sz // 2
    quadrants = [(0, 0, half, half), (half, 0, sz, half),
                 (0, half, half, sz), (half, half, sz, sz)]
    mask_ear_l = np.zeros((sz, sz), dtype=np.uint8)
    mask_ear_l[:int(sz * 0.40), :int(sz * 0.35)] = mask_full[:int(sz * 0.40), :int(sz * 0.35)]
    mask_ear_r = np.zeros((sz, sz), dtype=np.uint8)
    mask_ear_r[:int(sz * 0.40), int(sz * 0.65):] = mask_full[:int(sz * 0.40), int(sz * 0.65):]

    def hist(src, ch, bins, rng, m, weight=1.0):
        h = cv2.calcHist([src], [ch], m, [bins], rng).flatten()
        h /= (h.sum() + 1e-10)
        features.append(h * weight)

    hist(hsv, 0, 30, [0, 180], mask_full)
    hist(hsv, 1, 12, [0, 256], mask_full)
    hist(lab, 0, 12, [0, 256], mask_full)
    hist(lab, 1, 12, [0, 256], mask_full)
    hist(lab, 2, 12, [0, 256], mask_full)
    quad_weights = [1.5, 1.5, 0.5, 0.5]
    for qi, (x1, y1, x2, y2) in enumerate(quadrants):
        w = quad_weights[qi]
        mask_q = np.zeros((sz, sz), dtype=np.uint8)
        mask_q[y1:y2, x1:x2] = mask_full[y1:y2, x1:x2]
        hist(hsv, 0, 20, [0, 180], mask_q, w)
        hist(hsv, 1, 8, [0, 256], mask_q, w)
        hist(lab, 1, 8, [0, 256], mask_q, w)
        hist(lab, 2, 8, [0, 256], mask_q, w)
    hist(hsv, 0, 30, [0, 180], mask_hair, 4.0)
    hist(hsv, 1, 16, [0, 256], mask_hair, 4.0)
    hist(lab, 0, 12, [0, 256], mask_hair, 3.0)
    hist(lab, 1, 16, [0, 256], mask_hair, 4.0)
    hist(lab, 2, 16, [0, 256], mask_hair, 4.0)
    for mask_ear in [mask_ear_l, mask_ear_r]:
        hist(hsv, 0, 20, [0, 180], mask_ear, 3.0)
        hist(hsv, 1, 10, [0, 256], mask_ear, 3.0)
        hist(lab, 1, 10, [0, 256], mask_ear, 3.0)
        hist(lab, 2, 10, [0, 256], mask_ear, 3.0)
    hist(hsv, 0, 20, [0, 180], mask_face, 2.0)
    hist(hsv, 1, 12, [0, 256], mask_face, 2.0)
    hist(lab, 1, 12, [0, 256], mask_face, 2.0)
    hist(lab, 2, 12, [0, 256], mask_face, 2.0)
    hist(hsv, 0, 16, [0, 180], mask_body, 0.5)
    hist(hsv, 1, 8, [0, 256], mask_body, 0.5)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx ** 2 + gy ** 2)
    angle = (np.arctan2(gy, gx) * 180 / np.pi + 180) % 360
    for mask_r, n_bins, w in [(mask_hair, 18, 3.0), (mask_full, 18, 1.0), (mask_face, 12, 1.5)]:
        mb = mask_r > 0
        mg, ag = mag[mb], angle[mb]
        if len(mg) > 0:
            hog = np.zeros(n_bins, dtype=np.float32)
            bins = (ag / (360.0 / n_bins)).astype(int) % n_bins
            np.add.at(hog, bins, mg)
            hog /= (hog.sum() + 1e-10)
            features.append(hog * w)
        else:
            features.append(np.zeros(n_bins, dtype=np.float32))
    for mask_ear in [mask_ear_l, mask_ear_r]:
        mb = mask_ear > 0
        mg, ag = mag[mb], angle[mb]
        if len(mg) > 0:
            hog = np.zeros(12, dtype=np.float32)
            bins = (ag / 30.0).astype(int) % 12
            np.add.at(hog, bins, mg)
            hog /= (hog.sum() + 1e-10)
            features.append(hog * 3.0)
        else:
            features.append(np.zeros(12, dtype=np.float32))
    hair_crop = gray[:int(sz * 0.40), :]
    hair_mask_crop = mask_full[:int(sz * 0.40), :]
    hair_masked = cv2.bitwise_and(hair_crop, hair_mask_crop)
    hair_small = cv2.resize(hair_masked, (12, 8), interpolation=cv2.INTER_AREA)
    features.append(hair_small.flatten().astype(np.float32) / 255.0 * 2.0)
    edges = cv2.Canny(gray, 50, 120)
    hair_edges = cv2.bitwise_and(edges, mask_hair)
    hair_edges_small = cv2.resize(hair_edges, (16, 8), interpolation=cv2.INTER_AREA)
    features.append(hair_edges_small.flatten().astype(np.float32) / 255.0 * 3.0)
    for mask_ear in [mask_ear_l, mask_ear_r]:
        ear_edges = cv2.bitwise_and(edges, mask_ear)
        ear_edges_small = cv2.resize(ear_edges, (8, 8), interpolation=cv2.INTER_AREA)
        features.append(ear_edges_small.flatten().astype(np.float32) / 255.0 * 3.0)
    face_edges = cv2.bitwise_and(edges, mask_face)
    face_edges_small = cv2.resize(face_edges, (12, 8), interpolation=cv2.INTER_AREA)
    features.append(face_edges_small.flatten().astype(np.float32) / 255.0 * 2.0)
    full_edges = cv2.bitwise_and(edges, mask_full)
    full_edges_small = cv2.resize(full_edges, (16, 16), interpolation=cv2.INTER_AREA)
    features.append(full_edges_small.flatten().astype(np.float32) / 255.0)
    mag_u8 = np.clip(mag, 0, 255).astype(np.uint8)
    mag_masked = cv2.bitwise_and(mag_u8, mask_hair)
    mag_small = cv2.resize(mag_masked, (14, 8), interpolation=cv2.INTER_AREA)
    features.append(mag_small.flatten().astype(np.float32) / 255.0 * 2.0)
    return np.concatenate(features).astype(np.float32)


class CharacterDetector:
    def __init__(self):
        self.names = []
        self.feat_normed = None
        self.sift_descriptors = {}
        self.sift = cv2.SIFT_create(nfeatures=100)
        self.bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
        if BAKED_PATH.exists():
            self.load_baked()
        else:
            self.load_templates()

    def load_baked(self):
        with open(BAKED_PATH, "rb") as f:
            data = pickle.load(f)
        self.names = data["names"]
        self.feat_normed = data["feat_normed"]
        self.sift_descriptors = data["sift_descriptors"]

    def load_templates(self):
        templates = {}
        for p in sorted(TEMPLATE_DIR.glob("*.png")):
            img = cv2.imread(str(p))
            if img is None:
                continue
            h, w = img.shape[:2]
            cx, cy = w // 2, h // 2
            r = min(cx, cy) - 2
            x1, y1 = max(0, cx - r), max(0, cy - r)
            x2, y2 = min(w, cx + r), min(h, cy + r)
            portrait = cv2.resize(img[y1:y2, x1:x2], (92, 92), interpolation=cv2.INTER_AREA)
            feat = compute_features(portrait)
            templates[p.stem] = feat
            gray = cv2.cvtColor(portrait, cv2.COLOR_BGR2GRAY)
            sz = portrait.shape[0]
            mask = np.zeros((sz, sz), dtype=np.uint8)
            cv2.circle(mask, (sz // 2, sz // 2), sz // 2 - 6, 255, -1)
            kp, des = self.sift.detectAndCompute(gray, mask)
            self.sift_descriptors[p.stem] = des
        self.names = list(templates.keys())
        feat_stack = np.stack([templates[n] for n in self.names])
        norms = np.linalg.norm(feat_stack, axis=1, keepdims=True)
        self.feat_normed = feat_stack / np.maximum(norms, 1e-10)

    def sift_match_count(self, des_query, des_tpl):
        if des_query is None or des_tpl is None:
            return 0
        if len(des_query) < 2 or len(des_tpl) < 2:
            return 0
        matches = self.bf.knnMatch(des_query, des_tpl, k=2)
        good = 0
        for pair in matches:
            if len(pair) == 2 and pair[0].distance < 0.70 * pair[1].distance:
                good += 1
        return good

    def get_sift_descriptors(self, img_bgr):
        sz = img_bgr.shape[0]
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        mask = np.zeros((sz, sz), dtype=np.uint8)
        cv2.circle(mask, (sz // 2, sz // 2), sz // 2 - 6, 255, -1)
        kp, des = self.sift.detectAndCompute(gray, mask)
        return kp, des

    def detect(self, portrait_bgr):
        feat = compute_features(portrait_bgr)
        feat_n = feat / (np.linalg.norm(feat) + 1e-10)
        scores = self.feat_normed @ feat_n
        top_idx = np.argsort(scores)[::-1][:5]
        kp_q, des_q = self.get_sift_descriptors(portrait_bgr)
        best_name = self.names[top_idx[0]]
        best_combined = -1.0
        for idx in top_idx:
            name = self.names[idx]
            cos_score = float(scores[idx])
            sift_count = self.sift_match_count(des_q, self.sift_descriptors[name])
            combined = cos_score + sift_count * 0.008
            if combined > best_combined:
                best_combined = combined
                best_name = name
        return best_name, best_combined

    def detect_facility(self, img, slot_config):
        results = []
        cx = slot_config["circle_cx"]
        cy = slot_config["circle_cy"]
        cr = slot_config["circle_r"]
        for i in range(slot_config["num_slots"]):
            y1 = slot_config["base_y"] + i * slot_config["inc"]
            y2 = y1 + slot_config["height"]
            x1 = slot_config["base_x"]
            x2 = x1 + slot_config["width"]
            if y2 > img.shape[0] or x2 > img.shape[1]:
                continue
            roi = img[y1:y2, x1:x2]
            if not has_portrait_circle(roi, cx, cy, cr):
                results.append((i, None, 0.0))
                continue
            portrait = extract_circle_from_roi(roi, cx, cy, cr)
            name, score = self.detect(portrait)
            results.append((i, name, score))
        return results
