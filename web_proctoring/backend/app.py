from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import cv2
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BACKEND_DIR, "..", ".."))
sys.path.append(os.path.join(PROJECT_ROOT, "cheating_detector"))
from engine import ProctoringEngine

app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app)

engine = ProctoringEngine()
engine_running = False
engine_thread = None
RECORDINGS_ROOT = os.path.join(PROJECT_ROOT, "cheating_detector", "recordings")
LEGACY_RECORDINGS_ROOT = os.path.join(PROJECT_ROOT, "web_proctoring", "backend", "recordings")
BROWSER_RECORDINGS_ROOT = os.path.join(RECORDINGS_ROOT, "_browser")
os.makedirs(BROWSER_RECORDINGS_ROOT, exist_ok=True)

DEFAULT_USERS = [
    ("student1", "student123", "student", "Student One", ""),
    ("teacher1", "teacher123", "teacher", "Teacher One", "DEFAULT_TEACHER_CODE"),
]

EXAMS = [
    {
        "exam_id": "EXAM-001",
        "title": "General Aptitude and Programming Assessment",
        "duration_minutes": 60,
        "questions": [
            {
                "id": "q1",
                "text": "What is 2 + 2?",
                "options": ["2", "3", "4", "5"],
            },
            {
                "id": "q2",
                "text": "Select the color of the sky on a clear day.",
                "options": ["Green", "Blue", "Black", "Orange"],
            },
            {
                "id": "q3",
                "text": "Python is a ...",
                "options": ["Database", "Programming language", "Browser", "Protocol"],
            },
            {
                "id": "q4",
                "text": "Which data structure uses FIFO order?",
                "options": ["Stack", "Queue", "Tree", "Graph"],
            },
            {
                "id": "q5",
                "text": "What is the time complexity of binary search?",
                "options": ["O(n)", "O(log n)", "O(n log n)", "O(1)"],
            },
            {
                "id": "q6",
                "text": "Which SQL statement is used to retrieve data?",
                "options": ["UPDATE", "DELETE", "SELECT", "INSERT"],
            },
            {
                "id": "q7",
                "text": "HTML stands for:",
                "options": [
                    "Hyper Text Markup Language",
                    "HighText Machine Language",
                    "Hyper Transfer Markup Logic",
                    "Home Tool Markup Language",
                ],
            },
            {
                "id": "q8",
                "text": "Which keyword is used to define a function in Python?",
                "options": ["func", "define", "def", "lambda"],
            },
            {
                "id": "q9",
                "text": "Which protocol is used for secure web traffic?",
                "options": ["HTTP", "FTP", "SSH", "HTTPS"],
            },
            {
                "id": "q10",
                "text": "Which one is a NoSQL database?",
                "options": ["MySQL", "MongoDB", "PostgreSQL", "SQLite"],
            },
            {
                "id": "q11",
                "text": "In OOP, inheritance is used to:",
                "options": [
                    "Hide implementation",
                    "Reuse existing class behavior",
                    "Increase compile time",
                    "Delete objects",
                ],
            },
            {
                "id": "q12",
                "text": "Which command initializes a new Git repository?",
                "options": ["git start", "git init", "git create", "git new"],
            },
        ],
    }
]

SESSIONS = {}
ATTEMPTS = {}
EVALUATIONS = []
ACTIVE_ATTEMPT_BY_STUDENT = {}
SUBMISSION_RESULTS = {}
SUBMISSION_LOCK = threading.Lock()

SESSION_DATA_PATH = os.path.join(os.path.dirname(__file__), "session_data.json")
AUTH_DB_PATH = os.path.join(os.path.dirname(__file__), "auth.db")

EVENT_WEIGHTS = {
    "TAB_SWITCH": 0.18,
    "WINDOW_BLUR": 0.12,
    "COPY_ATTEMPT": 0.10,
    "PASTE_ATTEMPT": 0.16,
    "DEVTOOLS_ATTEMPT": 0.30,
    "CAMERA_OFF": 0.60,
    "FULLSCREEN_EXIT": 0.35,
    "RIGHT_CLICK_BLOCKED": 0.06,
}

# Final cheating-risk fusion weights.
# Both channels contribute to final score.
VISION_WEIGHT = 0.55
BEHAVIOR_WEIGHT = 0.45


def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _auth_db_conn():
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db():
    with _auth_db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student', 'teacher')),
                name TEXT NOT NULL,
                teacher_code TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.executemany(
            """
            INSERT OR IGNORE INTO users (username, password, role, name, teacher_code)
            VALUES (?, ?, ?, ?, ?)
            """,
            DEFAULT_USERS,
        )
        conn.commit()


def get_user_by_username(username):
    with _auth_db_conn() as conn:
        row = conn.execute(
            "SELECT username, password, role, name, teacher_code FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def create_user(username, password, role, name, teacher_code):
    try:
        with _auth_db_conn() as conn:
            conn.execute(
                """
                INSERT INTO users (username, password, role, name, teacher_code)
                VALUES (?, ?, ?, ?, ?)
                """,
                (username, password, role, name, teacher_code),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _normalize_question_rows(raw_questions):
    if not isinstance(raw_questions, list) or not raw_questions:
        raise ValueError("questions must be a non-empty list")

    def _normalize_correct_option(raw_value):
        value = str(raw_value or "").strip().lower()
        if value.startswith("correct[") and value.endswith("]") and len(value) == 10:
            value = value[8]
        return value

    cleaned = []
    for idx, q in enumerate(raw_questions, start=1):
        if not isinstance(q, dict):
            raise ValueError("Each question must be an object")
        text = (q.get("text") or "").strip()
        options = q.get("options") or []
        if not text:
            raise ValueError("Each question needs text")
        if not isinstance(options, list) or len(options) != 4:
            raise ValueError("Each question needs exactly 4 options (A, B, C, D)")
        cleaned_options = [str(opt).strip() for opt in options if str(opt).strip()]
        if len(cleaned_options) != 4:
            raise ValueError("Each question needs exactly 4 non-empty options")
        correct_option = _normalize_correct_option(q.get("correct_option"))
        if correct_option not in {"a", "b", "c", "d"}:
            raise ValueError("Each question must include correct_option as one of: a, b, c, d")
        cleaned.append(
            {
                "id": f"q{idx}",
                "text": text,
                "options": cleaned_options,
                "correct_option": correct_option,
            }
        )
    return cleaned


def init_exam_db():
    with _auth_db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exams (
                exam_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL,
                teacher_username TEXT NOT NULL,
                questions_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exam_assignments (
                exam_id TEXT NOT NULL,
                student_username TEXT NOT NULL,
                assigned_at TEXT NOT NULL,
                PRIMARY KEY (exam_id, student_username)
            )
            """
        )

        default_exam = EXAMS[0]
        conn.execute(
            """
            INSERT OR IGNORE INTO exams (
                exam_id, title, duration_minutes, start_at, end_at,
                teacher_username, questions_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                default_exam["exam_id"],
                default_exam["title"],
                int(default_exam["duration_minutes"]),
                "2026-01-01T09:00:00",
                "2026-12-31T18:00:00",
                "teacher1",
                json.dumps(default_exam["questions"]),
                now_iso(),
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO exam_assignments (exam_id, student_username, assigned_at)
            VALUES (?, ?, ?)
            """,
            (default_exam["exam_id"], "student1", now_iso()),
        )
        conn.commit()


def list_students():
    with _auth_db_conn() as conn:
        rows = conn.execute(
            "SELECT username, name FROM users WHERE role='student' ORDER BY username"
        ).fetchall()
    return [dict(row) for row in rows]


def list_teacher_exams(teacher_username):
    with _auth_db_conn() as conn:
        rows = conn.execute(
            """
            SELECT e.exam_id, e.title, e.duration_minutes, e.start_at, e.end_at, e.created_at,
                   e.questions_json,
                   GROUP_CONCAT(a.student_username, ',') AS assignees
            FROM exams e
            LEFT JOIN exam_assignments a ON a.exam_id = e.exam_id
            WHERE e.teacher_username = ?
            GROUP BY e.exam_id
            ORDER BY e.created_at DESC
            """,
            (teacher_username,),
        ).fetchall()

    result = []
    for row in rows:
        item = dict(row)
        questions = json.loads(item["questions_json"])
        assignees = [u for u in (item["assignees"] or "").split(",") if u]
        result.append(
            {
                "exam_id": item["exam_id"],
                "title": item["title"],
                "duration_minutes": item["duration_minutes"],
                "start_at": item["start_at"],
                "end_at": item["end_at"],
                "created_at": item["created_at"],
                "question_count": len(questions),
                "assigned_students": assignees,
                "questions": questions,
            }
        )
    return result


def create_exam(teacher_username, title, duration_minutes, start_at, end_at, questions, students):
    questions_clean = _normalize_question_rows(questions)
    start_dt = _parse_iso_datetime(start_at)
    end_dt = _parse_iso_datetime(end_at)
    if not start_dt or not end_dt:
        raise ValueError("start_at and end_at must be valid ISO datetimes")
    if end_dt <= start_dt:
        raise ValueError("end_at must be after start_at")
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be greater than 0")
    if not students:
        raise ValueError("Assign at least one student")

    student_set = {u.strip() for u in students if u and u.strip()}
    if not student_set:
        raise ValueError("Assign at least one student")
    assign_all = any(u.lower() == "all" for u in student_set)

    with _auth_db_conn() as conn:
        if assign_all:
            valid_rows = conn.execute(
                "SELECT username FROM users WHERE role='student' ORDER BY username"
            ).fetchall()
            valid_students = {r["username"] for r in valid_rows}
            if not valid_students:
                raise ValueError("No students found to assign")
        else:
            valid_rows = conn.execute(
                "SELECT username FROM users WHERE role='student' AND username IN ({})".format(
                    ",".join("?" for _ in student_set)
                ),
                tuple(student_set),
            ).fetchall()
            valid_students = {r["username"] for r in valid_rows}
            missing = sorted(student_set - valid_students)
            if missing:
                raise ValueError(f"Unknown student username(s): {', '.join(missing)}")

        exam_id = "EXAM-" + secrets.token_hex(4).upper()
        conn.execute(
            """
            INSERT INTO exams (
                exam_id, title, duration_minutes, start_at, end_at,
                teacher_username, questions_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exam_id,
                title.strip(),
                int(duration_minutes),
                start_dt.isoformat(timespec="seconds"),
                end_dt.isoformat(timespec="seconds"),
                teacher_username,
                json.dumps(questions_clean),
                now_iso(),
            ),
        )
        conn.executemany(
            """
            INSERT INTO exam_assignments (exam_id, student_username, assigned_at)
            VALUES (?, ?, ?)
            """,
            [(exam_id, username, now_iso()) for username in sorted(valid_students)],
        )
        conn.commit()
    return exam_id


def list_assigned_exams(student_username):
    with _auth_db_conn() as conn:
        rows = conn.execute(
            """
            SELECT e.exam_id, e.title, e.duration_minutes, e.start_at, e.end_at, e.questions_json
            FROM exams e
            INNER JOIN exam_assignments a ON a.exam_id = e.exam_id
            WHERE a.student_username = ?
            ORDER BY e.start_at ASC, e.created_at ASC
            """,
            (student_username,),
        ).fetchall()
    exams = []
    now_dt = datetime.now()
    for row in rows:
        item = dict(row)
        start_dt = _parse_iso_datetime(item["start_at"])
        end_dt = _parse_iso_datetime(item["end_at"])
        status = "available"
        if start_dt and now_dt < start_dt:
            status = "upcoming"
        elif end_dt and now_dt > end_dt:
            status = "closed"
        exams.append(
            {
                "exam_id": item["exam_id"],
                "title": item["title"],
                "duration_minutes": item["duration_minutes"],
                "start_at": item["start_at"],
                "end_at": item["end_at"],
                "questions": json.loads(item["questions_json"]),
                "status": status,
            }
        )
    return exams


def get_exam_for_student(exam_id, student_username):
    with _auth_db_conn() as conn:
        row = conn.execute(
            """
            SELECT e.exam_id, e.title, e.duration_minutes, e.start_at, e.end_at, e.questions_json
            FROM exams e
            INNER JOIN exam_assignments a ON a.exam_id = e.exam_id
            WHERE e.exam_id = ? AND a.student_username = ?
            """,
            (exam_id, student_username),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["questions"] = json.loads(item.pop("questions_json"))
    return item


init_auth_db()
init_exam_db()


def save_snapshot():
    payload = {
        "sessions_count": len(SESSIONS),
        "attempts_count": len(ATTEMPTS),
        "evaluations_count": len(EVALUATIONS),
        "updated_at": now_iso(),
    }
    with open(SESSION_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def auth_user(required_role=None):
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    session = SESSIONS.get(token)
    if not session:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    if required_role and session["role"] != required_role:
        return None, (jsonify({"error": "Forbidden"}), 403)
    return session, None


def ensure_active_attempt(student_username):
    attempt_id = ACTIVE_ATTEMPT_BY_STUDENT.get(student_username)
    if not attempt_id:
        return None
    attempt = ATTEMPTS.get(attempt_id)
    if not attempt:
        return None
    if attempt["status"] != "running":
        return None
    return attempt


def compute_behavior_score(events):
    score = 0.0
    counts = {}
    for event in events:
        event_type = event["event"]
        counts[event_type] = counts.get(event_type, 0) + 1
        base = EVENT_WEIGHTS.get(event_type, 0.03)
        # Escalate repeated behavior events so repeated violations are reflected strongly.
        repeat_multiplier = 1.0 + 0.50 * (counts[event_type] - 1)
        score += base * repeat_multiplier
    return min(score, 1.0), counts


def compute_final_risk(vision_prob, behavior_prob):
    return min(1.0, VISION_WEIGHT * vision_prob + BEHAVIOR_WEIGHT * behavior_prob)


def compute_exam_score(questions, answers):
    letter_to_idx = {"a": 0, "b": 1, "c": 2, "d": 3}
    total = 0
    correct = 0
    for q in questions or []:
        qid = q.get("id")
        options = q.get("options") or []
        correct_opt = str(q.get("correct_option") or "").strip().lower()
        if qid is None or len(options) < 4 or correct_opt not in letter_to_idx:
            continue
        total += 1
        idx = letter_to_idx[correct_opt]
        expected = str(options[idx]).strip().lower()
        got = str((answers or {}).get(qid, "")).strip().lower()
        if got and got == expected:
            correct += 1
    percent = round((correct / total) * 100.0, 2) if total > 0 else 0.0
    return correct, total, percent


def latest_student_evaluation(student_username, exam_id):
    for item in reversed(EVALUATIONS):
        if item.get("student_username") == student_username and item.get("exam_id") == exam_id:
            return item
    return None


def _transcode_to_browser_mp4(source_path):
    source_abs = os.path.abspath(source_path)
    browser_root_abs = os.path.abspath(BROWSER_RECORDINGS_ROOT)
    source_ext = os.path.splitext(source_path)[1].lower()
    try:
        already_browser_file = (
            os.path.commonpath([source_abs, browser_root_abs]) == browser_root_abs
            and source_ext == ".mp4"
        )
    except ValueError:
        already_browser_file = False
    if already_browser_file:
        return source_path

    stem = os.path.splitext(os.path.basename(source_path))[0]
    if stem.endswith("_browser"):
        base_name = f"{stem}.mp4"
    else:
        base_name = f"{stem}_browser.mp4"
    target_path = os.path.join(BROWSER_RECORDINGS_ROOT, base_name)

    if os.path.exists(target_path) and os.path.getmtime(target_path) >= os.path.getmtime(source_path):
        return target_path

    ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_exe = None

    if ffmpeg_exe:
        cmd = [
            ffmpeg_exe,
            "-y",
            "-i",
            source_path,
            "-c:v",
            "libx264",
            "-profile:v",
            "baseline",
            "-level",
            "3.1",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            target_path,
        ]
        try:
            completed = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                text=True,
            )
            if completed.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                return target_path
        except OSError:
            pass

    # Fallback when ffmpeg is unavailable: keep source; playback may depend on browser codec support.
    return source_path


def build_browser_video_url(saved_video_path):
    if not saved_video_path or not os.path.exists(saved_video_path):
        return None, None

    playback_path = resolve_original_recording(saved_video_path) or saved_video_path

    abs_playback = os.path.abspath(playback_path)
    abs_root = os.path.abspath(RECORDINGS_ROOT)
    inside_root = False
    try:
        inside_root = os.path.commonpath([abs_playback, abs_root]) == abs_root
    except ValueError:
        inside_root = False
    if not inside_root:
        base = os.path.basename(playback_path)
        stem, ext = os.path.splitext(base)
        migrated_name = f"{stem}_legacy{ext}"
        migrated_path = os.path.join(BROWSER_RECORDINGS_ROOT, migrated_name)
        if not os.path.exists(migrated_path):
            try:
                os.replace(playback_path, migrated_path)
            except OSError:
                return None, None
        playback_path = migrated_path

    converted = _transcode_to_browser_mp4(playback_path)
    if converted and os.path.exists(converted):
        playback_path = converted

    if not os.path.exists(playback_path):
        return None, None

    rel = os.path.relpath(playback_path, RECORDINGS_ROOT).replace("\\", "/")
    return rel, f"/recordings/{rel}"


def resolve_recording_source(item):
    rel = (item.get("video_relative_path") or "").strip()
    if rel:
        rel_fs = rel.replace("/", os.sep)
        for root in (RECORDINGS_ROOT, LEGACY_RECORDINGS_ROOT):
            path = os.path.join(root, rel_fs)
            if os.path.exists(path):
                return path

    url = (item.get("video_url") or "").strip()
    if url:
        rec_token = "/recordings/"
        idx = url.find(rec_token)
        if idx >= 0:
            tail = url[idx + len(rec_token):]
            tail_fs = tail.replace("/", os.sep)
            for root in (RECORDINGS_ROOT, LEGACY_RECORDINGS_ROOT):
                path = os.path.join(root, tail_fs)
                if os.path.exists(path):
                    return path
    return None


def resolve_original_recording(path):
    if not path:
        return None

    abs_path = os.path.abspath(path)
    browser_root_abs = os.path.abspath(BROWSER_RECORDINGS_ROOT)
    try:
        inside_browser_root = os.path.commonpath([abs_path, browser_root_abs]) == browser_root_abs
    except ValueError:
        inside_browser_root = False
    if not inside_browser_root:
        return path if os.path.exists(path) else None

    stem, _ = os.path.splitext(os.path.basename(path))
    while stem.endswith("_browser"):
        stem = stem[: -len("_browser")]
    if stem.endswith("_legacy"):
        stem = stem[: -len("_legacy")]

    search_dirs = [
        RECORDINGS_ROOT,
        os.path.join(RECORDINGS_ROOT, "strong"),
        os.path.join(RECORDINGS_ROOT, "STRONG"),
        os.path.join(RECORDINGS_ROOT, "suspicious"),
        os.path.join(RECORDINGS_ROOT, "SUSPICIOUS"),
        LEGACY_RECORDINGS_ROOT,
        os.path.join(LEGACY_RECORDINGS_ROOT, "strong"),
        os.path.join(LEGACY_RECORDINGS_ROOT, "STRONG"),
        os.path.join(LEGACY_RECORDINGS_ROOT, "suspicious"),
        os.path.join(LEGACY_RECORDINGS_ROOT, "SUSPICIOUS"),
    ]
    for folder in search_dirs:
        for ext in (".mp4", ".avi"):
            candidate = os.path.join(folder, f"{stem}{ext}")
            if os.path.exists(candidate):
                return candidate
    return path if os.path.exists(path) else None


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    return jsonify({"error": f"Server error: {str(exc)}"}), 500


def run_engine_loop():
    global engine_running
    while engine_running:
        engine.update()
        time.sleep(0.03)


@app.route("/")
def serve_frontend():
    return send_from_directory(app.static_folder, "exam.html")


@app.route("/recordings/<path:subpath>")
def serve_recording(subpath):
    primary = os.path.join(RECORDINGS_ROOT, subpath.replace("/", os.sep))
    if not os.path.exists(primary):
        legacy = os.path.join(LEGACY_RECORDINGS_ROOT, subpath.replace("/", os.sep))
        if os.path.exists(legacy):
            return send_from_directory(LEGACY_RECORDINGS_ROOT, subpath)
    return send_from_directory(RECORDINGS_ROOT, subpath)


@app.route("/web_proctoring/backend/recordings/<path:subpath>")
def serve_legacy_recording_url(subpath):
    return serve_recording(subpath)


@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "").strip()

    user = get_user_by_username(username)
    if not user or user["password"] != password or user["role"] != role:
        return jsonify({"error": "Invalid credentials"}), 401

    token = secrets.token_hex(16)
    SESSIONS[token] = {
        "username": username,
        "role": user["role"],
        "name": user["name"],
        "created_at": now_iso(),
    }
    save_snapshot()
    return jsonify(
        {
            "token": token,
            "role": user["role"],
            "name": user["name"],
            "username": username,
        }
    )


@app.route("/auth/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()
    role = (data.get("role") or "student").strip()
    teacher_code = (data.get("teacher_code") or "").strip()

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400
    if get_user_by_username(username):
        return jsonify({"error": "username already exists"}), 409
    if role not in {"student", "teacher"}:
        return jsonify({"error": "role must be student or teacher"}), 400
    if role == "teacher" and not teacher_code:
        return jsonify({"error": "teacher_code is required for teacher signup"}), 400

    inserted = create_user(
        username=username,
        password=password,
        role=role,
        name=(name or username),
        teacher_code=(teacher_code if role == "teacher" else ""),
    )
    if not inserted:
        return jsonify({"error": "username already exists"}), 409
    save_snapshot()
    return jsonify({"status": "signup_success", "username": username, "role": role})


@app.route("/student/current_exam", methods=["GET"])
def student_current_exam():
    session, err = auth_user(required_role="student")
    if err:
        return err
    exams = list_assigned_exams(session["username"])
    if not exams:
        return jsonify({"exam": None, "student": session["name"]})
    return jsonify({"exam": exams[0], "student": session["name"]})


@app.route("/student/exams", methods=["GET"])
def student_exams():
    session, err = auth_user(required_role="student")
    if err:
        return err
    exams = list_assigned_exams(session["username"])
    for exam in exams:
        eval_item = latest_student_evaluation(session["username"], exam["exam_id"])
        exam["result_available"] = bool(eval_item)
    return jsonify({"exams": exams})


@app.route("/student/results/<exam_id>", methods=["GET"])
def student_result_by_exam(exam_id):
    session, err = auth_user(required_role="student")
    if err:
        return err
    eval_item = latest_student_evaluation(session["username"], exam_id)
    if not eval_item:
        return jsonify({"error": "Result not available for this exam"}), 404
    return jsonify(
        {
            "result": {
                "exam_id": eval_item.get("exam_id"),
                "exam_title": eval_item.get("exam_title", eval_item.get("exam_id")),
                "submitted_at": eval_item.get("submitted_at"),
                "score_correct": eval_item.get("score_correct", 0),
                "score_total": eval_item.get("score_total", 0),
                "score_percent": eval_item.get("score_percent", 0.0),
            }
        }
    )


@app.route("/exam/start", methods=["POST"])
def start_exam():
    global engine_running, engine_thread
    session, err = auth_user(required_role="student")
    if err:
        return err
    data = request.get_json(silent=True) or {}
    exam_id = (data.get("exam_id") or "").strip()
    if not exam_id:
        return jsonify({"error": "exam_id is required"}), 400
    exam = get_exam_for_student(exam_id, session["username"])
    if not exam:
        return jsonify({"error": "Exam not assigned to this student"}), 404

    existing = ensure_active_attempt(session["username"])
    if existing:
        return jsonify({"error": "Exam already running"}), 409

    now_dt = datetime.now()
    start_dt = _parse_iso_datetime(exam["start_at"])
    end_dt = _parse_iso_datetime(exam["end_at"])
    if start_dt and now_dt < start_dt:
        return jsonify({"error": "Exam is not open yet"}), 409
    if end_dt and now_dt > end_dt:
        return jsonify({"error": "Exam window has closed"}), 409

    try:
        engine.start_exam()
    except Exception as exc:
        return jsonify({"error": f"Unable to start proctoring engine: {str(exc)}"}), 500
    engine_running = True
    engine_thread = threading.Thread(target=run_engine_loop, daemon=True)
    engine_thread.start()
    attempt_id = secrets.token_hex(8)
    attempt = {
        "attempt_id": attempt_id,
        "student_username": session["username"],
        "student_name": session["name"],
        "exam_id": exam["exam_id"],
        "exam_title": exam["title"],
        "started_at": now_iso(),
        "submitted_at": None,
        "status": "running",
        "events": [],
        "answers": {},
    }
    ATTEMPTS[attempt_id] = attempt
    ACTIVE_ATTEMPT_BY_STUDENT[session["username"]] = attempt_id
    save_snapshot()

    return jsonify({"status": "exam_started", "attempt_id": attempt_id})


@app.route("/exam/event", methods=["POST"])
def log_event():
    session, err = auth_user(required_role="student")
    if err:
        return err

    attempt = ensure_active_attempt(session["username"])
    if not attempt:
        return jsonify({"error": "No active exam"}), 409

    data = request.get_json(silent=True) or {}
    event_type = (data.get("event") or "").strip()
    meta = data.get("meta") or {}
    if not event_type:
        return jsonify({"error": "event is required"}), 400

    attempt["events"].append(
        {
            "event": event_type,
            "meta": meta,
            "timestamp": now_iso(),
        }
    )
    return jsonify({"status": "logged"})


@app.route("/exam/submit", methods=["POST"])
def submit_exam():
    global engine_running
    session, err = auth_user(required_role="student")
    if err:
        return err

    data = request.get_json(silent=True) or {}
    fallback_id = (data.get("attempt_id") or "").strip()
    if fallback_id and fallback_id in SUBMISSION_RESULTS:
        cached_attempt = ATTEMPTS.get(fallback_id)
        if cached_attempt and cached_attempt.get("student_username") == session["username"]:
            return jsonify(SUBMISSION_RESULTS[fallback_id])

    attempt = ensure_active_attempt(session["username"])
    if not attempt:
        # Fallback path: recover active attempt by explicit attempt_id when mapping/state drifts.
        if fallback_id:
            candidate = ATTEMPTS.get(fallback_id)
            if (
                candidate
                and candidate.get("student_username") == session["username"]
                and candidate.get("status") in {"running", "submitting"}
            ):
                attempt = candidate
                ACTIVE_ATTEMPT_BY_STUDENT[session["username"]] = fallback_id
    if not attempt:
        return jsonify({"error": "No active exam"}), 409

    with SUBMISSION_LOCK:
        cached = SUBMISSION_RESULTS.get(attempt["attempt_id"])
        if cached:
            return jsonify(cached)
        if attempt.get("status") == "submitting":
            return jsonify({"error": "Submission is already being processed. Please wait."}), 409
        if attempt.get("status") != "running":
            return jsonify({"error": "No active exam"}), 409
        attempt["status"] = "submitting"
        save_snapshot()

    answers = data.get("answers") or {}
    attempt["answers"] = answers
    attempt["submitted_at"] = now_iso()
    exam = get_exam_for_student(attempt["exam_id"], session["username"])
    questions = (exam or {}).get("questions", [])
    score_correct, score_total, score_percent = compute_exam_score(questions, answers)
    behavior_prob, event_counts = compute_behavior_score(attempt["events"])

    engine_running = False
    time.sleep(0.05)
    vision_prob, video_saved, case_type = engine.stop_exam(keep_review_recording=True)
    final_prob = compute_final_risk(vision_prob, behavior_prob)

    if final_prob > 0.72 or behavior_prob >= 0.72:
        risk_level = "strong"
    elif final_prob >= 0.45 or behavior_prob >= 0.45:
        risk_level = "suspicious"
    else:
        risk_level = "normal"

    saved_video_path = engine.last_saved_video
    video_relative_path = None
    video_url = None
    if saved_video_path and os.path.exists(saved_video_path):
        video_relative_path, video_url = build_browser_video_url(saved_video_path)

    evaluation = {
        "attempt_id": attempt["attempt_id"],
        "student_username": attempt["student_username"],
        "student_name": attempt["student_name"],
        "exam_id": attempt["exam_id"],
        "exam_title": attempt.get("exam_title", attempt["exam_id"]),
        "started_at": attempt["started_at"],
        "submitted_at": attempt["submitted_at"],
        "score_correct": score_correct,
        "score_total": score_total,
        "score_percent": score_percent,
        "vision_probability": round(float(vision_prob), 3),
        "behavior_probability": round(float(behavior_prob), 3),
        "final_probability": round(float(final_prob), 3),
        "engine_case_type": case_type,
        "risk_level": risk_level,
        "video_saved": bool(video_saved),
        "video_relative_path": video_relative_path,
        "video_url": video_url,
        "event_counts": event_counts,
        "total_events": len(attempt["events"]),
    }
    EVALUATIONS.append(evaluation)
    attempt["status"] = "submitted"
    ACTIVE_ATTEMPT_BY_STUDENT.pop(session["username"], None)
    result_payload = {
        "status": "submitted",
        "attempt_id": attempt["attempt_id"],
        "submitted_at": attempt["submitted_at"],
    }
    SUBMISSION_RESULTS[attempt["attempt_id"]] = result_payload
    save_snapshot()

    return jsonify(result_payload)


@app.route("/teacher/evaluations", methods=["GET"])
def teacher_evaluations():
    _, err = auth_user(required_role="teacher")
    if err:
        return err
    risk = (request.args.get("risk") or "all").strip().lower()
    # Backfill browser-playable URLs for older evaluations (e.g., AVI history).
    for item in EVALUATIONS:
        source = resolve_recording_source(item)
        if not source:
            continue
        browser_rel, browser_url = build_browser_video_url(source)
        if browser_url:
            item["video_relative_path"] = browser_rel
            item["video_url"] = browser_url

    if risk in {"strong", "suspicious", "normal"}:
        rows = [item for item in EVALUATIONS if item["risk_level"] == risk]
    else:
        rows = EVALUATIONS
    return jsonify({"evaluations": rows})


@app.route("/teacher/exams", methods=["GET"])
def teacher_exams():
    session, err = auth_user(required_role="teacher")
    if err:
        return err
    return jsonify({"exams": list_teacher_exams(session["username"])})


@app.route("/teacher/students", methods=["GET"])
def teacher_students():
    _, err = auth_user(required_role="teacher")
    if err:
        return err
    return jsonify({"students": list_students()})


@app.route("/teacher/exams", methods=["POST"])
def teacher_create_exam():
    session, err = auth_user(required_role="teacher")
    if err:
        return err

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    try:
        duration_minutes = int(data.get("duration_minutes") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "duration_minutes must be an integer"}), 400
    start_at = (data.get("start_at") or "").strip()
    end_at = (data.get("end_at") or "").strip()
    questions = data.get("questions") or []
    assigned_students = data.get("assigned_students") or []

    if not title:
        return jsonify({"error": "title is required"}), 400

    try:
        exam_id = create_exam(
            teacher_username=session["username"],
            title=title,
            duration_minutes=duration_minutes,
            start_at=start_at,
            end_at=end_at,
            questions=questions,
            students=assigned_students,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"status": "created", "exam_id": exam_id})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
