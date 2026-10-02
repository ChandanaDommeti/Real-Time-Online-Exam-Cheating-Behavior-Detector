import numpy as np

class ProbabilityFusion:
    def sigmoid(self, x):
        return 1 / (1 + np.exp(-x))

    def compute(self, face_absence, phone_persist, gaze_duration, talking_duration):
        """
        Inputs are normalized ratios (0–1)
        """

        # Base weighted score
        base_score = (
            0.25 * face_absence +
            0.30 * phone_persist +
            0.20 * gaze_duration +
            0.25 * talking_duration
        )

        # Non-linear amplification
        amplified = self.sigmoid(base_score * 7)

        return amplified
