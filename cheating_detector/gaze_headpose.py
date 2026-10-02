import cv2
import mediapipe as mp

mp_face_mesh = mp.solutions.face_mesh

class GazeHeadPose:
    def __init__(self):
        self.face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=3, 
            refine_landmarks=True
        )
        # Temporal smoothing to prevent single-frame spikes from triggering gaze-away.
        self.gaze_ema = 0.0
        self.GAZE_EMA_ALPHA = 0.25

    def process(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb)

        face_count = 0
        gaze_away = 0

        if results.multi_face_landmarks:
            face_count = len(results.multi_face_landmarks)

            landmarks = results.multi_face_landmarks[0].landmark
            # Head yaw proxy: nose offset from eye midpoint, normalized by face width.
            left_eye_outer = landmarks[33]
            right_eye_outer = landmarks[263]
            nose = landmarks[1]
            face_left = landmarks[234]
            face_right = landmarks[454]

            face_width = abs(face_right.x - face_left.x)
            if face_width < 1e-6:
                face_width = 1e-6

            eye_mid_x = (left_eye_outer.x + right_eye_outer.x) / 2.0
            yaw_offset = abs(nose.x - eye_mid_x) / face_width
            head_away = yaw_offset > 0.22

            # Optional iris-based check (refine_landmarks=True provides iris points).
            iris_away = False
            if len(landmarks) > 473:
                left_iris = landmarks[468]
                right_iris = landmarks[473]
                left_eye_inner = landmarks[133]
                right_eye_inner = landmarks[362]

                left_den = (left_eye_inner.x - left_eye_outer.x)
                right_den = (right_eye_outer.x - right_eye_inner.x)
                if abs(left_den) < 1e-6:
                    left_den = 1e-6
                if abs(right_den) < 1e-6:
                    right_den = 1e-6

                left_ratio = (left_iris.x - left_eye_outer.x) / left_den
                right_ratio = (right_eye_outer.x - right_iris.x) / right_den

                left_off = left_ratio < 0.18 or left_ratio > 0.82
                right_off = right_ratio < 0.18 or right_ratio > 0.82
                iris_away = left_off and right_off

            raw_away = 1.0 if (head_away or iris_away) else 0.0
            self.gaze_ema = (
                self.GAZE_EMA_ALPHA * raw_away +
                (1.0 - self.GAZE_EMA_ALPHA) * self.gaze_ema
            )
            gaze_away = 1 if self.gaze_ema >= 0.65 else 0
        else:
            # Decay state when no face is visible.
            self.gaze_ema *= 0.8

        return gaze_away, face_count
