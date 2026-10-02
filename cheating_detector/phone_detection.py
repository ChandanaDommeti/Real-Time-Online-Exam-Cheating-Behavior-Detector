from ultralytics import YOLO

class PhoneDetector:
    def __init__(self):
        self.model = YOLO("yolov8n.pt")
        self.MIN_CONF = 0.15

        # COCO class IDs mapped to display labels.
        self.FORBIDDEN_CLASSES = {
            67: "PHONE",
            73: "BOOK",
            63: "LAPTOP"
        }

    def process(self, frame):
        results = self.model(frame, verbose=False)
        violation_detected = 0
        detected_labels = set()

        for r in results:
            if r.boxes is None:
                continue

            for box in r.boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])

                if cls in self.FORBIDDEN_CLASSES and conf >= self.MIN_CONF:
                    violation_detected = 1
                    detected_labels.add(self.FORBIDDEN_CLASSES[cls])

        return violation_detected, sorted(detected_labels)
