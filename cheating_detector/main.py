import cv2
from engine import ProctoringEngine

engine = ProctoringEngine()
exam_started = False

print("S → Start | E → End | ESC → Exit")

while True:
    frame = engine.get_preview_frame()

    if frame is not None:
        # Process and record a clean frame before adding UI overlays.
        if exam_started:
            engine.update(frame.copy())

        if not exam_started:
            cv2.putText(
                frame,
                "Press S to START Exam",
                (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2
            )
        else:
            cv2.putText(
                frame,
                "Exam Running - Press E to END",
                (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 0, 255),
                2
            )

        cv2.imshow("Online Exam Proctoring", frame)

    key = cv2.waitKey(1) & 0xFF

    # -------- START EXAM --------
    if key in (ord('s'), ord('S')) and not exam_started:
        exam_started = True
        engine.start_exam()
        print("Exam Started")

    # -------- END EXAM --------
    if key in (ord('e'), ord('E')) and exam_started:
        exam_started = False
        prob, saved, case_type = engine.stop_exam()

        print("\nFINAL CHEATING PROBABILITY:", prob)
        print("CASE TYPE:", case_type)
        print("VIDEO SAVED:", saved)

    # -------- EXIT --------
    if key == 27:  # ESC
        break

if engine.cap is not None:
    engine.cap.release()
cv2.destroyAllWindows()
