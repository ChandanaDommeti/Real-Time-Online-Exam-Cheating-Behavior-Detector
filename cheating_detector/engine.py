import cv2
import os
import time
from gaze_headpose import GazeHeadPose
from phone_detection import PhoneDetector
from talking_detection import TalkingDetector
from probability_fusion import ProbabilityFusion

class ProctoringEngine:
    def __init__(self):
        self.cap = None
        self.last_camera_error = ""
        self.camera_source = ""
        self.gaze_model = GazeHeadPose()
        self.phone_model = PhoneDetector()
        self.talking_model = TalkingDetector()
        self.fusion = ProbabilityFusion()

        self.exam_running = False
        self.video_writer = None
        self.video_path = None
        self.last_saved_video = None

        self.multi_face_frames = 0
        self.face_missing_frames = 0
        self.gaze_away_frames = 0
        self.phone_frames = 0
        self.talking_frames = 0
        self.total_frames = 0
        self.gaze_raw_frames = 0
        self.phone_raw_frames = 0

        self.face_missing_streak = 0
        self.gaze_away_streak = 0
        self.phone_streak = 0
        self.talking_streak = 0

        self.FPS = 20
        self.SUSPICIOUS_MIN = 0.70
        self.STRONG_MIN = 0.85
        self.CLIP_PADDING_SECONDS = 1.0

        self.FACE_GRACE = 20
        self.GAZE_GRACE = 6
        self.PHONE_GRACE = 4
        self.TALK_GRACE = 10

        self.recordings_root = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "recordings"
        )
        self.suspicious_dir = os.path.join(self.recordings_root, "suspicious")
        self.strong_dir = os.path.join(self.recordings_root, "strong")

        os.makedirs(self.recordings_root, exist_ok=True)
        os.makedirs(self.suspicious_dir, exist_ok=True)
        os.makedirs(self.strong_dir, exist_ok=True)

        self.suspicious_ranges = []
        self.current_suspicious_start = None
        self.frame_labels = {}
        self.last_saved_video = None

    def _open_camera_with_fallback(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

        backend_candidates = [(None, "DEFAULT")]
        if hasattr(cv2, "CAP_DSHOW"):
            backend_candidates.append((cv2.CAP_DSHOW, "DSHOW"))
        if hasattr(cv2, "CAP_MSMF"):
            backend_candidates.append((cv2.CAP_MSMF, "MSMF"))
        backend_candidates.append((cv2.CAP_ANY, "ANY"))

        errors = []
        for cam_index in (0, 1, 2):
            for backend_id, backend_name in backend_candidates:
                if backend_id is None:
                    cap = cv2.VideoCapture(cam_index)
                else:
                    cap = cv2.VideoCapture(cam_index, backend_id)
                if not cap.isOpened():
                    errors.append(f"idx={cam_index},backend={backend_name}:open_failed")
                    cap.release()
                    continue

                frame = None
                for _ in range(20):
                    ret, temp_frame = cap.read()
                    if ret and temp_frame is not None:
                        frame = temp_frame
                        break
                    time.sleep(0.05)

                if frame is not None:
                    self.cap = cap
                    self.camera_source = f"index={cam_index}, backend={backend_name}"
                    self.last_camera_error = ""
                    return frame

                errors.append(f"idx={cam_index},backend={backend_name}:read_failed")
                cap.release()

        self.last_camera_error = "; ".join(errors)
        return None

    def _read_frame(self):
        if self.cap is None or not self.cap.isOpened():
            return self._open_camera_with_fallback()

        for _ in range(3):
            ret, frame = self.cap.read()
            if ret and frame is not None:
                return frame
            time.sleep(0.02)

        return self._open_camera_with_fallback()

    def start_exam(self):
        self.exam_running = True

        self.multi_face_frames = 0
        self.face_missing_frames = 0
        self.gaze_away_frames = 0
        self.phone_frames = 0
        self.talking_frames = 0
        self.total_frames = 0
        self.gaze_raw_frames = 0
        self.phone_raw_frames = 0

        self.face_missing_streak = 0
        self.gaze_away_streak = 0
        self.phone_streak = 0
        self.talking_streak = 0
        self.suspicious_ranges = []
        self.current_suspicious_start = None
        self.frame_labels = {}

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.video_path = os.path.join(self.recordings_root, f"session_{timestamp}.mp4")

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        frame = self._read_frame()

        if frame is None:
            self.exam_running = False
            extra = (
                f" Camera probe details: {self.last_camera_error}."
                if self.last_camera_error else ""
            )
            raise RuntimeError(
                "Camera frame unavailable. Check Windows Camera privacy (allow desktop apps), "
                "and close camera-holding apps." + extra
            )

        h, w, _ = frame.shape
        self.video_writer = cv2.VideoWriter(
            self.video_path, fourcc, self.FPS, (w, h)
        )

    def update(self, frame=None):
        if not self.exam_running:
            return

        if frame is None:
            frame = self._read_frame()
            if frame is None:
                # Treat camera-feed loss during active exam as suspicious absence.
                self.total_frames += 1
                self.face_missing_streak += 1
                if self.face_missing_streak > self.FACE_GRACE:
                    self.face_missing_frames += 1
                return

        gaze_away, face_count = self.gaze_model.process(frame)
        phone_present, object_labels = self.phone_model.process(frame)
        talking_present = self.talking_model.process(frame)

        self.total_frames += 1
        if gaze_away == 1:
            self.gaze_raw_frames += 1
        if phone_present == 1:
            self.phone_raw_frames += 1

        # Face absence
                # ---------- MULTI FACE DETECTION ----------
        if face_count > 1:
            self.multi_face_frames += 1

        # ---------- FACE ABSENCE ----------
        if face_count == 0:
            self.face_missing_streak += 1
            if self.face_missing_streak > self.FACE_GRACE:
                self.face_missing_frames += 1
        else:
            self.face_missing_streak = 0


        # Gaze away
        if gaze_away == 1:
            self.gaze_away_streak += 1
            if self.gaze_away_streak > self.GAZE_GRACE:
                self.gaze_away_frames += 1
        else:
            self.gaze_away_streak = 0

        # Phone
        if phone_present == 1:
            self.phone_streak += 1
            if self.phone_streak > self.PHONE_GRACE:
                self.phone_frames += 1
        else:
            self.phone_streak = 0

        # Talking
        if talking_present == 1:
            self.talking_streak += 1
            if self.talking_streak > self.TALK_GRACE:
                self.talking_frames += 1
        else:
            self.talking_streak = 0

        labels = []
        if face_count > 1:
            labels.append("MULTI FACE")
        if self.face_missing_streak > self.FACE_GRACE:
            labels.append("FACE MISSING")
        if self.gaze_away_streak > self.GAZE_GRACE:
            labels.append("GAZE AWAY")
        for object_label in object_labels:
            labels.append(f"OBJECT: {object_label}")
        if self.phone_streak > self.PHONE_GRACE:
            labels.append("PROHIBITED OBJECT PERSISTENCE")
        if self.talking_streak > self.TALK_GRACE:
            labels.append("TALKING")

        frame_idx = self.total_frames - 1
        if labels:
            self.frame_labels[frame_idx] = labels

        suspicious_now = bool(labels)
        self._update_suspicious_ranges(self.total_frames - 1, suspicious_now)

        self.video_writer.write(frame)

    def _update_suspicious_ranges(self, frame_idx, suspicious_now):
        if suspicious_now:
            if self.current_suspicious_start is None:
                self.current_suspicious_start = frame_idx
            return

        if self.current_suspicious_start is not None:
            self.suspicious_ranges.append(
                (self.current_suspicious_start, frame_idx - 1)
            )
            self.current_suspicious_start = None

    def _finalize_suspicious_ranges(self):
        if self.current_suspicious_start is not None:
            self.suspicious_ranges.append(
                (self.current_suspicious_start, self.total_frames - 1)
            )
            self.current_suspicious_start = None

    def _expanded_suspicious_ranges(self):
        if not self.suspicious_ranges:
            return []

        pad = int(self.FPS * self.CLIP_PADDING_SECONDS)
        expanded = []
        for start, end in self.suspicious_ranges:
            expanded.append(
                (max(0, start - pad), min(self.total_frames - 1, end + pad))
            )

        expanded.sort(key=lambda item: item[0])
        merged = [expanded[0]]
        for start, end in expanded[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end + 1:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged

    def _write_labeled_video(self, source_path, target_path, ranges=None):
        cap = cv2.VideoCapture(source_path)
        if not cap.isOpened():
            return False

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = self.FPS

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(target_path, fourcc, fps, (width, height))

        frame_idx = 0
        range_idx = 0
        ok, frame = cap.read()
        while ok:
            write_frame = True
            if ranges is not None:
                while range_idx < len(ranges) and frame_idx > ranges[range_idx][1]:
                    range_idx += 1
                if range_idx >= len(ranges):
                    break
                start, end = ranges[range_idx]
                write_frame = start <= frame_idx <= end

            if write_frame:
                labels = self.frame_labels.get(frame_idx)
                if labels:
                    y = 35
                    for label in labels:
                        cv2.putText(
                            frame,
                            label,
                            (15, y),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.8,
                            (0, 0, 255),
                            2
                        )
                        y += 30
                writer.write(frame)

            frame_idx += 1
            ok, frame = cap.read()

        cap.release()
        writer.release()
        return True

    def _write_suspicious_only_video(self, source_path, target_path):
        ranges = self._expanded_suspicious_ranges()
        if not ranges:
            return False
        return self._write_labeled_video(source_path, target_path, ranges=ranges)

    def stop_exam(self, keep_review_recording=False):
        self.exam_running = False

        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        if self.cap is not None:
            self.cap.release()
            self.cap = None

        if self.total_frames == 0:
            self.last_saved_video = None
            return 0.0, False, "no_data"

        self._finalize_suspicious_ranges()

        face_absence = self.face_missing_frames / self.total_frames
        gaze_duration = self.gaze_away_frames / self.total_frames
        phone_persist = self.phone_frames / self.total_frames
        gaze_raw_ratio = self.gaze_raw_frames / self.total_frames
        phone_raw_ratio = self.phone_raw_frames / self.total_frames
        talking_duration = self.talking_frames / self.total_frames

        # Blend persistent+raw evidence so intermittent cheating does not get ignored.
        effective_gaze = max(gaze_duration, gaze_raw_ratio * 0.60)
        effective_phone = max(phone_persist, phone_raw_ratio * 0.70)

        vision_prob = self.fusion.compute(
            face_absence, effective_phone, effective_gaze, talking_duration
        )

        # ---------- HARD ESCALATION ----------
        multi_face_ratio = self.multi_face_frames / max(1, self.total_frames)

        if multi_face_ratio > 0.08:   # >8% of exam time
            vision_prob = max(vision_prob, 0.90)
        if phone_raw_ratio > 0.03:
            vision_prob = max(vision_prob, 0.75)
        if phone_raw_ratio > 0.08:
            vision_prob = max(vision_prob, 0.90)
        if face_absence > 0.12:
            vision_prob = max(vision_prob, 0.78)
        if face_absence > 0.20:
            vision_prob = max(vision_prob, 0.90)
        if effective_gaze > 0.30:
            vision_prob = max(vision_prob, 0.80)
        if effective_gaze > 0.45:
            vision_prob = max(vision_prob, 0.90)

        # Final clamp
        vision_prob = min(vision_prob, 1.0)


        if self.SUSPICIOUS_MIN < vision_prob < self.STRONG_MIN:
            target_path = os.path.join(self.suspicious_dir, os.path.basename(self.video_path))
            clip_saved = self._write_suspicious_only_video(
                self.video_path, target_path
            )
            if clip_saved and os.path.exists(self.video_path):
                os.remove(self.video_path)
                self.last_saved_video = target_path
            else:
                # Fallback: keep full recording so teacher can still review.
                if os.path.exists(self.video_path):
                    os.replace(self.video_path, target_path)
                    clip_saved = True
                    self.last_saved_video = target_path
            case_type = "suspicious"
            video_saved = clip_saved
        elif vision_prob >= self.STRONG_MIN:
            target_path = os.path.join(self.strong_dir, os.path.basename(self.video_path))
            clip_saved = self._write_labeled_video(self.video_path, target_path)
            if clip_saved and os.path.exists(self.video_path):
                os.remove(self.video_path)
                self.last_saved_video = target_path
            else:
                if os.path.exists(self.video_path):
                    os.replace(self.video_path, target_path)
                    clip_saved = True
                    self.last_saved_video = target_path
            case_type = "strong"
            video_saved = clip_saved
        else:
            if keep_review_recording and os.path.exists(self.video_path):
                target_path = os.path.join(self.suspicious_dir, os.path.basename(self.video_path))
                try:
                    os.replace(self.video_path, target_path)
                except OSError:
                    target_path = self.video_path
                self.last_saved_video = target_path
                video_saved = True
            else:
                if os.path.exists(self.video_path):
                    os.remove(self.video_path)
                self.last_saved_video = None
                video_saved = False
            case_type = "normal"

        return round(vision_prob, 3), video_saved, case_type
    def get_preview_frame(self):
        frame = self._read_frame()
        if frame is None:
            return None
        return frame
