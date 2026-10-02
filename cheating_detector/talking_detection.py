import cv2
import mediapipe as mp

mp_face_mesh = mp.solutions.face_mesh


class TalkingDetector:
    def __init__(self):
        self.face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True
        )
        self.mouth_open_threshold = 0.06

    def process(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb)

        if not results.multi_face_landmarks:
            return 0

        landmarks = results.multi_face_landmarks[0].landmark

        # Mouth openness normalized by inter-eye distance.
        mouth_upper = landmarks[13]
        mouth_lower = landmarks[14]
        left_eye = landmarks[33]
        right_eye = landmarks[263]

        eye_dist = abs(left_eye.x - right_eye.x)
        if eye_dist <= 1e-6:
            return 0

        mouth_open_ratio = abs(mouth_lower.y - mouth_upper.y) / eye_dist
        return 1 if mouth_open_ratio > self.mouth_open_threshold else 0
