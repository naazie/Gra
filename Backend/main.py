

"""
GraphMind — Backend API v11.0  (ABSOLUTE PEAK)

New in v11:
  ─── CURRICULUM GRAPH ──────────────────────────────────────────────────────
  - Pre-built CS knowledge dependency graph (50 topics, 44 edges)
  - Prerequisites looked up from reliable graph, not just LLM inference
  - Curriculum topics have difficulty levels for calibration

  ─── INTERVIEW SIMULATOR ───────────────────────────────────────────────────
  - POST /interview/start   — begin a mock interview session
  - POST /interview/respond — turn-by-turn interviewer dialogue
  - GET  /interview/score   — end-of-session scorecard
  - Difficulty calibration based on past performance
  - Misconception detection mid-answer
  - ATTEMPTED / MISTAKE_IN / CONFIRMS edges stored

  ─── TUTOR ENGINE ──────────────────────────────────────────────────────────
  - GET  /readiness/{username}  — live readiness percentage
  - POST /study-plan            — week-by-week plan from gap analysis
  - GET  /review/{username}     — spaced repetition: what needs review
  - GET  /brief/{username}      — daily session-start brief

  ─── TUTOR INTELLIGENCE ────────────────────────────────────────────────────
  - Learning style detection from first 3 interactions
  - Progress recognition: notices improvement on past weak spots
  - Active recall mode built into mentor persona
  - Improved forgetting curve: e^(-λt/(1+reinforcement*0.3))
  - CONFIRMS, DERIVED_FROM, MISTAKE_IN edges in graph

  ─── FIXES ────────────────────────────────────────────────────────────────
  - Requirements cache: Gemini called once per topic lifetime
  - Ollama primary for answer generation (rate-limit safe)
  - /memory/forget JWT enforced
  - Improved contradiction: graph + content + stated vs demonstrated
"""

import re
import os
import sys
import json
import time
import uuid
import asyncio
import logging
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import (
    FastAPI, Depends, HTTPException, UploadFile, File, Form,
    BackgroundTasks, Header, Body,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text

current_dir  = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import database as db
from graph_engine import GraphEngine
from orchestrator import handle_user_input, init_orchestrator, _get_embedder, _get_faiss
from ingestion.pipeline import IngestionPipeline
from retrieval.query_engine import QueryEngine
from retrieval.answer_generator import (
    generate_answer, generate_answer_async, _build_human_citations,
    ACTIVE_RECALL_INSTRUCTION, FEYNMAN_INSTRUCTION, SYSTEM_PERSONA,
)
from input_validator import sanitize, has_injection, check_english, is_semantic_duplicate
from backtracker import needs_backtracking, build_mcq, build_final_plan_prompt, compute_gaps_for_topic, detect_intent
from requirement_fetcher import (
    fetch_requirements, fetch_company_requirements,
    cross_check_with_memory, get_cache_stats,
)
from conversation_manager import (
    add_message as cm_add, format_for_prompt,
    clear_session as cm_clear, get_recent,
)
from session_state import (
    get_state, set_gap_queue, get_active_gap, advance_gap,
    increment_turns, should_ask_next_gap, get_context_summary,
    set_active_mcq, get_active_mcq, record_mcq_answer, get_mcq_answers, set_all_mcqs, get_all_mcqs,
    consume_gaps_complete, goal_already_triggered,
    clear_session as clear_sess,
)
from memory_acknowledger import generate_acknowledgement
from curriculum_graph import (
    seed_curriculum, get_curriculum_prerequisites,
    get_topic_difficulty,
)
from interview_simulator import (
    start_interview, get_interview_state, is_interview_active,
    end_interview, generate_interview_question, respond_as_interviewer,
    generate_scorecard, detect_misconception,
)
from tutor_engine import (
    detect_learning_style, get_style_instruction,
    get_topics_needing_review, compute_readiness_score,
    generate_daily_brief, generate_study_plan,
    detect_progress,
)
from mongo_store import (
    save_message, get_sessions, get_session_messages,
    delete_session, is_available as mongo_available,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="GraphMind: AI Tutor + Long-Term Memory",
    description="Learning Path Planner + Interview Prep — WCE Hackathon 2026",
    version="11.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ── Startup ────────────────────────────────────────────────────────────────────
pipeline     = IngestionPipeline()
graph        = GraphEngine()
init_orchestrator(graph)
query_engine = QueryEngine()
db.init_db()

# Seed curriculum graph at startup
try:
    seed_curriculum(graph, verbose=True)
except Exception as e:
    logger.warning(f"Curriculum seeding skipped: {e}")

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# ── Auth helpers ───────────────────────────────────────────────────────────────

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return db.create_access_token({"sub": username, "exp": expire.timestamp()})


def _verify_token(authorization: str = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid token")
    token = authorization.split(" ", 1)[1]
    try:
        from jose import jwt
        payload  = jwt.decode(token, db.SECRET_KEY, algorithms=[db.ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(401, "Invalid token payload")
        return username
    except Exception:
        raise HTTPException(401, "Token expired or invalid")


# ══════════════════════════════════════════════════════════════════════════════
#  HEALTH
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    def _neo4j():
        try:
            with graph.driver.session() as s: s.run("RETURN 1")
            return {"status": "healthy"}
        except Exception as e: return {"status": "unhealthy", "error": str(e)}
    def _pg():
        try:
            s = db.SessionLocal()
            try: s.execute(sql_text("SELECT 1"))
            finally: s.close()
            return {"status": "healthy"}
        except Exception as e: return {"status": "unhealthy", "error": str(e)}
    def _ollama():
        try:
            r = requests.get(
                f"{os.getenv('OLLAMA_BASE_URL','http://localhost:11434')}/api/tags", timeout=5
            )
            r.raise_for_status()
            return {"status": "healthy"}
        except Exception as e: return {"status": "unhealthy", "error": str(e)}

    n, p, o = _neo4j(), _pg(), _ollama()
    overall = "healthy" if all(s["status"] == "healthy" for s in [n, p, o]) else "degraded"
    return {
        "status": overall,
        "services": {"neo4j": n, "postgres": p, "ollama": o},
        "mongo_available":  mongo_available(),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "cache_stats":       get_cache_stats(),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/register")
def register(username: str, password: str, session: Session = Depends(get_db)):
    t0 = time.time()
    username = sanitize(username)
    if not username or len(username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters")
    if session.query(db.User).filter(db.User.username == username).first():
        raise HTTPException(400, "User already exists")
    session.add(db.User(username=username, password=db.get_password_hash(password)))
    session.commit()
    graph.add_user(username)
    return {
        "message": "User registered",
        "token": _make_token(username),
        "username": username,
        "execution_time_ms": round((time.time()-t0)*1000, 2),
    }


@app.post("/login")
def login(username: str, password: str, session: Session = Depends(get_db)):
    t0   = time.time()
    user = session.query(db.User).filter(db.User.username == username).first()
    if not user or not db.verify_password(password, str(user.password)):
        raise HTTPException(401, "Invalid credentials")
    return {
        "message": "Login successful",
        "token": _make_token(username),
        "username": username,
        "execution_time_ms": round((time.time()-t0)*1000, 2),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CHAT HISTORY (MongoDB)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/chats")
async def list_chats(username: str = Depends(_verify_token)):
    return {"sessions": get_sessions(username, limit=30)}

@app.get("/chats/{session_id}")
async def get_chat(session_id: str, username: str = Depends(_verify_token)):
    return {"session_id": session_id, "messages": get_session_messages(username, session_id)}

@app.delete("/chats/{session_id}")
async def delete_chat(session_id: str, username: str = Depends(_verify_token)):
    return {"deleted": delete_session(username, session_id)}

@app.post("/chat/new")
async def new_chat(username: str = Depends(_verify_token)):
    sid = str(uuid.uuid4())
    cm_clear(sid)
    clear_sess(sid)
    return {"session_id": sid}


# ══════════════════════════════════════════════════════════════════════════════
#  MEMORY INGESTION (JWT required)
# ══════════════════════════════════════════════════════════════════════════════

async def _do_ingest(username: str, text: str):
    t0   = time.time()
    text = sanitize(text)
    if not text: raise HTTPException(400, "Empty input")
    if has_injection(text): raise HTTPException(400, "Input rejected")
    _, corrected, corrections = check_english(text)
    if corrections: text = corrected
    try:
        is_dup, existing = is_semantic_duplicate(text, _get_embedder(), _get_faiss(), username)
        if is_dup:
            return {"success": False, "duplicate": True, "existing": existing, "corrections": corrections}
    except Exception:
        pass
    graph.add_user(username)
    nodes = pipeline.ingest(user_id=username, raw_text=text)
    return {
        "success": True, "nodes_created": len(nodes),
        "edges_created": len(nodes),
        "preview": [str(n.get("text",""))[:80] for n in nodes[:3]],
        "corrections": corrections,
        "execution_time_ms": round((time.time()-t0)*1000, 2),
    }

@app.post("/memory/ingest")
async def ingest_memory_spec(text: str, username: str = Depends(_verify_token)):
    try: return await _do_ingest(username, text)
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, str(e))

@app.post("/memory")
async def ingest_memory(text: str, username: str = Depends(_verify_token)):
    try: return await _do_ingest(username, text)
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, str(e))

# @app.post("/memory/file")
# async def ingest_file(
#     background_tasks: BackgroundTasks,
#     file: UploadFile = File(...),
#     username: str = Depends(_verify_token),
# ):
#     import tempfile, shutil
#     allowed = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".md"}
#     ext = os.path.splitext(file.filename or "")[1].lower()
#     if ext not in allowed:
#         raise HTTPException(400, f"File type '{ext}' not supported.")
#     try:
#         with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
#             shutil.copyfileobj(file.file, tmp)
#             tmp_path = tmp.name
#         graph.add_user(username)
#         def _run():
#             try:
#                 nodes = pipeline.ingest(user_id=username, file_path=tmp_path)
#                 logger.info(f"[file] {file.filename}: {len(nodes)} nodes")
#             finally:
#                 try: os.unlink(tmp_path)
#                 except: pass
#         if background_tasks:
#             background_tasks.add_task(_run)
#             return {"success": True, "message": f"'{file.filename}' received, processing.", "filename": file.filename}
#         _run()
#         return {"success": True, "filename": file.filename}
#     except HTTPException: raise
#     except Exception as e: raise HTTPException(500, str(e))

@app.post("/memory/file")
async def ingest_file(
    file: UploadFile = File(...),
    username: str = Depends(_verify_token),
):
    import tempfile, shutil

    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp", ".txt", ".md"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(400, f"File type '{ext}' not supported.")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        graph.add_user(username)

        nodes = pipeline.ingest(user_id=username, file_path=tmp_path)

        try:
            os.unlink(tmp_path)
        except:
            pass

        return {
            "success": True,
            "message": f"'{file.filename}' processed successfully.",
            "filename": file.filename,
            "nodes_created": len(nodes),
            "preview": nodes[:3],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/memory/forget/{username}")
async def trigger_forget(username: str = Depends(_verify_token)):
    try:
        archived = graph.forget_stale_memories(username=username)
        graph.compute_graph_scores()
        return {"archived_count": archived, "message": f"{archived} memories archived."}
    except Exception as e: raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  TUTOR INTELLIGENCE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/readiness/{username}")
async def get_readiness(username: str, goal: str = ""):
    """
    Live readiness score for the user's goal.
    Shown in topbar — updates as memories are added.
    """
    try:
        state = get_state(f"readiness_{username}")
        actual_goal = goal or state.get("current_goal", "software engineering interviews")

        reqs = await fetch_requirements(actual_goal)
        if not reqs:
            reqs = ["arrays", "recursion", "dynamic programming", "system design", "behavioral interviews"]

        readiness = await compute_readiness_score(
            graph, username, actual_goal, reqs, _get_embedder(), _get_faiss()
        )

        review_needed = get_topics_needing_review(graph, username)

        return {
            "readiness_pct": readiness["score"],
            "goal":          readiness["goal"],
            "strengths":     readiness["strengths"],
            "gaps":          readiness["gaps"],
            "review_needed": [r["content"] for r in review_needed[:3]],
            "breakdown":     readiness.get("breakdown", {}),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/study-plan")
async def create_study_plan(
    goal:         str  = Body(...),
    weeks:        int  = Body(default=6),
    hours_per_day: float = Body(default=2.0),
    username: str = Depends(_verify_token),
):
    """Generates a personalised week-by-week study plan from gap analysis."""
    try:
        reqs      = await fetch_requirements(goal)
        mem_check = cross_check_with_memory(reqs, _get_embedder(), _get_faiss(), username)
        gaps      = [t for t in reqs if not mem_check.get(t, False)]
        strengths = [t for t in reqs if mem_check.get(t, False)]
        plan      = await generate_study_plan(username, goal, gaps, weeks, hours_per_day, strengths)
        return {
            "plan":      plan,
            "goal":      goal,
            "gaps":      gaps[:6],
            "strengths": strengths[:4],
            "weeks":     weeks,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/review/{username}")
async def get_review_topics(username: str):
    """Topics that need spaced-repetition review right now."""
    try:
        topics = get_topics_needing_review(graph, username)
        return {"review_topics": topics}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/brief/{username}")
async def get_daily_brief(username: str, session_id: str = ""):
    """One-sentence session-start brief. Call when starting a new session."""
    try:
        state        = get_state(session_id or f"brief_{username}")
        goal         = state.get("current_goal", "software engineering interviews")
        reqs         = await fetch_requirements(goal)
        mem_check    = cross_check_with_memory(reqs, _get_embedder(), _get_faiss(), username)
        gaps         = [t for t in reqs if not mem_check.get(t, False)]
        review       = get_topics_needing_review(graph, username)

        readiness    = await compute_readiness_score(
            graph, username, goal, reqs, _get_embedder(), _get_faiss()
        )

        brief = await generate_daily_brief(
            username=username,
            goal=goal,
            readiness_pct=readiness["score"],
            top_gap=gaps[0] if gaps else "",
            days_since_last=1,
            review_needed=review,
        )
        return {"brief": brief, "readiness_pct": readiness["score"]}
    except Exception as e:
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  INTERVIEW SIMULATOR
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/interview/start")
async def start_interview_session(
    target_company: str = Body(default=""),
    question_type:  str = Body(default="coding"),
    username: str = Depends(_verify_token),
):
    """
    Starts a mock interview session.
    Returns session_id and the first question.
    """
    try:
        session_id = str(uuid.uuid4())

        # Get user's weak topics from graph
        past_mistakes = graph.get_past_mistakes(username, limit=5)
        weak_topics   = [m["topic"] for m in past_mistakes]

        # Start interview state
        start_interview(
            session_id=session_id,
            username=username,
            target_company=target_company or "a top tech company",
            weak_topics=weak_topics,
        )

        # Get user context for question generation
        user_memories = ""
        try:
            result = await handle_user_input(user_id=username, text=f"interview preparation {target_company}")
            user_memories = " ".join([e.get("text","")[:100] for e in result.get("evidence", [])[:3]])
        except Exception:
            pass

        # Generate first question
        question = await generate_interview_question(
            session_id=session_id,
            question_type=question_type,
            user_memories=user_memories,
        )

        # Store interview start as memory
        graph.add_user(username)
        if background_tasks_ref := None:
            pass
        pipeline.ingest(
            user_id=username,
            raw_text=f"Started a mock interview for {target_company or 'tech companies'}. Question type: {question_type}."
        )

        return {
            "session_id":    session_id,
            "question":      question,
            "company":       target_company or "tech company",
            "question_type": question_type,
            "message":       "Interview started. Take your time.",
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/interview/respond")
async def interview_respond(
    background_tasks: BackgroundTasks,
    session_id:   str = Body(...),
    answer:       str = Body(...),
    username: str = Depends(_verify_token),
):
    """
    User sends an answer. Interviewer responds.
    Also checks for misconceptions in the answer.
    """
    try:
        if not is_interview_active(session_id):
            raise HTTPException(400, "No active interview session. Start one with POST /interview/start")

        answer = sanitize(answer)
        state  = get_interview_state(session_id)

        # Get user memory context
        user_memories = ""
        try:
            result = await handle_user_input(user_id=username, text=answer[:200])
            user_memories = " ".join([e.get("text","")[:80] for e in result.get("evidence", [])[:2]])
        except Exception:
            pass

        # Check for misconception (runs in parallel with interviewer response)
        state = state or {}
        current_topic = state.get("current_topic", "")
        misconception_task = asyncio.create_task(
            detect_misconception(answer, current_topic)
        ) if current_topic else None

        # Get interviewer response
        response, is_done, _ = await respond_as_interviewer(
            session_id=session_id,
            user_answer=answer,
            user_memories=user_memories,
        )

        # Await misconception check
        misconception = None
        if misconception_task:
            try:
                misconception = await misconception_task
            except Exception:
                pass

        # Store attempt as memory
        if background_tasks:
            background_tasks.add_task(
                pipeline.ingest,
                user_id=username,
                raw_text=f"Interview answer about {current_topic}: {answer[:200]}",
            )

        result_payload = {
            "response":     response,
            "is_done":      is_done,
            "turn":         state.get("turn", 0),
            "max_turns":    state.get("max_turns", 12),
            "misconception": misconception,
        }

        if is_done:
            scorecard = await generate_scorecard(session_id, user_memories)
            result_payload["scorecard"] = scorecard
            end_interview(session_id)

            # Store scorecard as memory
            summary = scorecard.get("summary", "")
            if summary and background_tasks:
                background_tasks.add_task(
                    pipeline.ingest,
                    user_id=username,
                    raw_text=f"Mock interview completed. Score: {scorecard.get('overall', 5)}/10. {summary}",
                )

        return result_payload
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/interview/score/{session_id}")
async def get_interview_score(
    session_id: str,
    username: str = Depends(_verify_token),
):
    """Get scorecard for a completed interview."""
    try:
        scorecard = await generate_scorecard(session_id)
        return scorecard
    except Exception as e:
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  CHAT — THE PEAK ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/chat")
async def chat(
    background_tasks: BackgroundTasks,
    text:       str,
    stream:     bool = False,
    session_id: str  = "",
    username: str = Depends(_verify_token),
):
    t0 = time.time()

    # ── Sanitize ──────────────────────────────────────────────────────────────
    text = sanitize(text)
    if not text: raise HTTPException(400, "Empty input")
    if has_injection(text): raise HTTPException(400, "Input rejected")
    _, corrected_text, corrections = check_english(text)
    display_text = corrected_text if corrected_text else text

    if not session_id:
        session_id = str(uuid.uuid4())

    # ── Conversation history ──────────────────────────────────────────────────
    cm_add(session_id, "user", display_text)
    save_message(username, session_id, "user", display_text)

    # ── Learning style detection ──────────────────────────────────────────────
    recent_msgs = get_recent(session_id)
    if len(recent_msgs) <= 3:
        style = detect_learning_style([m["content"] for m in recent_msgs])
        get_state(session_id)["learning_style"] = style

    style_instruction = get_style_instruction(
        get_state(session_id).get("learning_style", "example_first")
    )

    try:
        # ── Retrieve ──────────────────────────────────────────────────────────
        result         = await handle_user_input(user_id=username, text=display_text)
        intent_profile = result["intent_profile"]
        evidence       = result["evidence"]
        retrieval_ms   = result["retrieval_ms"]
        is_query       = intent_profile.get("is_query", False)
        entities       = result.get("entities", [])
        conflict_alert = result.get("conflict_alert", "")

        # ── Citations with human-readable reasoning ────────────────────────────
        citations_payload = _build_human_citations(evidence)

        # ── Session context ────────────────────────────────────────────────────
        conversation_history = format_for_prompt(session_id)
        session_ctx          = get_context_summary(session_id)

        # ── Progress recognition ───────────────────────────────────────────────
        past_memory_texts = [e.get("text","") for e in evidence[:8]]
        progress_note     = detect_progress(display_text, past_memory_texts)

        # ── Backtracking v13 ─────────────────────────────────────────────────────
        active_gap  = get_active_gap(session_id)
        all_mcqs    = get_all_mcqs(session_id)

        # ── CASE 1: Batch MCQ answers incoming ────────────────────────────────
        if active_gap and all_mcqs:
            try:
                batch_answers = json.loads(display_text)
                is_batch = isinstance(batch_answers, dict)
            except Exception:
                batch_answers = {}
                is_batch = False

            if is_batch and batch_answers:
                goal_str = get_state(session_id).get("current_goal", display_text)

                for mcq_item in all_mcqs:
                    gap   = mcq_item["gap"]
                    label = batch_answers.get(gap, "").upper()
                    if label in ("A", "B", "C"):
                        opt_text = mcq_item["options"].get(label, "")
                        record_mcq_answer(session_id, gap, label, opt_text)
                        mem_text = (
                            f"For goal '{goal_str}', "
                            f"regarding '{gap}': user self-assessed as "
                            f"{label} — {opt_text}"
                        )
                        if background_tasks:
                            background_tasks.add_task(
                                pipeline.ingest, user_id=username, raw_text=mem_text
                            )

                while advance_gap(session_id) is not None:
                    pass
                consume_gaps_complete(session_id)

                mcq_answers = get_mcq_answers(session_id)
                plan_prompt = build_final_plan_prompt(goal_str, mcq_answers)
                correction_note = f"*(corrected: {'; '.join(corrections[:2])})*\n\n" if corrections else ""

                from retrieval.answer_generator import _ollama_generate
                llm_t0 = time.time()
                answer  = await asyncio.to_thread(_ollama_generate, plan_prompt)
                llm_ms  = round((time.time() - llm_t0) * 1000, 2)
                final_answer = correction_note + answer
                cm_add(session_id, "assistant", final_answer)
                save_message(username, session_id, "assistant", final_answer)
                return {
                    "answer": final_answer, "type": "final_plan",
                    "retrieval_time_ms": retrieval_ms,
                    "llm_generation_time_ms": llm_ms,
                    "total_time_ms": round((time.time() - t0) * 1000, 2),
                    "memory_citations": [], "entities": entities,
                    "intent_profile": intent_profile,
                    "corrections": corrections, "session_id": session_id,
                    "backtrack_active": False,
                }

        # ── CASE 2: No active MCQ — check if this request needs backtracking ──
        elif is_query and not active_gap:
            should_bt, gaps, goal_str = await needs_backtracking(
                query=display_text,
                entities=entities,
                username=username,
                session_id=session_id,
                graph_engine=graph,
                embedder=_get_embedder(),
                faiss_mgr=_get_faiss(),
            )
            if should_bt and gaps and entities:
                topic_str = entities[0] if entities else goal_str
                set_gap_queue(session_id, gaps, topic_str, goal=goal_str)

                mcq_tasks = [build_mcq(gap, goal_str) for gap in gaps]
                mcq_list  = await asyncio.gather(*mcq_tasks)

                for i, gap in enumerate(gaps):
                    mcq_list[i]["gap"] = gap

                set_active_mcq(session_id, gaps[0], mcq_list[0]["question"], mcq_list[0]["options"])
                set_all_mcqs(session_id, list(mcq_list))

                summary = f"[backtrack:{goal_str}]"
                cm_add(session_id, "assistant", summary)
                save_message(username, session_id, "assistant", summary)

                correction_note = f"*(corrected: {'; '.join(corrections[:2])})*\n\n" if corrections else ""
                return {
                    "answer": correction_note + "Before I build your plan, I need to understand your current level on a few key topics.",
                    "type": "backtrack_mcq",
                    "mcqs": list(mcq_list),
                    "retrieval_time_ms": retrieval_ms,
                    "llm_generation_time_ms": 0,
                    "total_time_ms": round((time.time() - t0) * 1000, 2),
                    "memory_citations": [], "entities": entities,
                    "intent_profile": intent_profile,
                    "corrections": corrections, "session_id": session_id,
                    "backtrack_active": True,
                }

        # ── Spaced repetition check ────────────────────────────────────────────
        review_topics = get_topics_needing_review(graph, username, threshold_days=5)
        review_note   = ""
        if review_topics and not active_gap:
            topic_name = review_topics[0]["content"][:40]
            freshness  = review_topics[0]["freshness_pct"]
            review_note = f"\n\nFYI: '{topic_name}' hasn't been reviewed in a while ({freshness}% fresh). Worth mentioning if natural."

        # ── Determine active recall / Feynman ─────────────────────────────────
        use_active_recall = (is_query and len(evidence) >= 3 and not active_gap)
        recall_instruction = ACTIVE_RECALL_INSTRUCTION if use_active_recall else ""

        # ── Build goal context for prompt ─────────────────────────────────────
        goal_context = ""
        state_goal = get_state(session_id).get("current_goal", "")
        if state_goal:
            goal_context = f"User's goal this session: {state_goal}"
        elif entities:
            goal_context = f"User's stated goal: {display_text[:100]}"

        # ── Correction note ────────────────────────────────────────────────────
        correction_note = f"*(corrected: {'; '.join(corrections[:2])})*\n\n" if corrections else ""

        # ══ MEMORY PATH (non-query) ════════════════════════════════════════════
        if not is_query:
            is_dup, existing = False, None
            try:
                is_dup, existing = is_semantic_duplicate(
                    display_text, _get_embedder(), _get_faiss(), username
                )
            except Exception:
                pass

            if is_dup:
                answer = (
                    f"I already have something very similar: \"{existing}\". "
                    "If this is different, give me more detail and I'll add it."
                )
            else:
                # Warm acknowledgement via Gemini
                answer = await generate_acknowledgement(
                    display_text, username,
                    recent_context=conversation_history,
                )
                graph.add_user(username)
                if background_tasks:
                    background_tasks.add_task(pipeline.ingest, user_id=username, raw_text=display_text)
                else:
                    pipeline.ingest(user_id=username, raw_text=display_text)

            if conflict_alert:
                answer = f"⚠️ {conflict_alert}\n\n{answer}"

            # Add progress recognition
            if progress_note:
                answer = progress_note + "\n\n" + answer

            final_answer = correction_note + answer
            cm_add(session_id, "assistant", final_answer)
            save_message(username, session_id, "assistant", final_answer)

            return {
                "answer": final_answer, "type": "memory",
                "retrieval_time_ms": retrieval_ms, "llm_generation_time_ms": 0,
                "total_time_ms": round((time.time()-t0)*1000, 2),
                "memory_citations": [], "entities": entities,
                "intent_profile": intent_profile, "conflict_alert": conflict_alert,
                "corrections": corrections, "session_id": session_id,
            }

        # ══ QUERY PATH ═════════════════════════════════════════════════════════
        sparse = len([e for e in evidence if e.get("text","").strip()]) < 2

        # Build enriched session context
        enriched_ctx = session_ctx
        if style_instruction:
            enriched_ctx += f" | Learning style: {style_instruction}"
        if review_note:
            enriched_ctx += review_note

        # Non-streaming
        if not stream:
            llm_t0 = time.time()

            answer = await generate_answer_async(
                query=display_text,
                evidence=evidence,
                conversation_history=conversation_history,
                session_context=enriched_ctx,
                backtrack_question="",
                goal_context=goal_context,
            )

            # Append active recall instruction to prompt handled inside generator
            # Add progress recognition before answer
            if progress_note:
                answer = progress_note + "\n\n" + answer

            if conflict_alert:
                answer = f"⚠️ {conflict_alert}\n\n{answer}"

            llm_ms       = round((time.time()-llm_t0)*1000, 2)
            final_answer = correction_note + answer

            cm_add(session_id, "assistant", final_answer)
            save_message(
                username, session_id, "assistant", final_answer,
                metadata={"retrieval_ms": retrieval_ms, "llm_ms": llm_ms,
                          "entities": entities},
            )

            if evidence:
                graph.reinforce_memories([e.get("node_id","") for e in evidence if e.get("node_id")])

            return {
                "answer": final_answer, "type": "query",
                "retrieval_time_ms": retrieval_ms,
                "llm_generation_time_ms": llm_ms,
                "total_time_ms": round((time.time()-t0)*1000, 2),
                "memory_citations": citations_payload,
                "entities": entities,
                "intent_profile": intent_profile,
                "conflict_alert": conflict_alert,
                "corrections": corrections,
                "session_id": session_id,
                "backtrack_active": False,   # only True when LLM was asked a prereq question this turn
                "review_suggested": [r["content"][:50] for r in review_topics[:2]],
            }

        # ── SSE Streaming ──────────────────────────────────────────────────────
        from retrieval.answer_generator import _build_memory_context
        memory_ctx  = _build_memory_context(evidence)
        parts       = [SYSTEM_PERSONA, f"\nLearning style note: {style_instruction}"]
        if enriched_ctx:   parts.append(f"\nCONTEXT: {enriched_ctx}")
        if conversation_history: parts.append(f"\n{conversation_history}")
        if goal_context:   parts.append(f"\nGOAL: {goal_context}")
        if memory_ctx:     parts.append(f"\nMEMORIES:\n{memory_ctx}")
        if sparse:         parts.append("\nYou don't have much on this — ask ONE specific question.")
       
        if use_active_recall: parts.append(ACTIVE_RECALL_INSTRUCTION)
        parts.append(f"\nUSER: {display_text}\n\nMENTOR:")
        prompt = "\n".join(parts)

        async def event_stream():
            meta = json.dumps({
                "type": "meta", "retrieval_ms": retrieval_ms,
                "entities": entities, "citations": citations_payload,
                "session_id": session_id, "corrections": corrections,
                "backtrack_active": False,   # only True when LLM was asked a prereq question this turn
                "review_suggested": [r["content"][:50] for r in review_topics[:2]],
            })
            yield f"data: {meta}\n\n"
            await asyncio.sleep(0)

            stream_t0     = time.time()
            full_response = []
            ollama_base   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            try:
                resp = requests.post(
                    f"{ollama_base}/api/generate",
                    json={"model": "llama3.1", "prompt": prompt, "stream": True,
                          "options": {"temperature": 0.5, "num_predict": 700}},
                    stream=True, timeout=180,
                )
                resp.raise_for_status()
                for line in resp.iter_lines(decode_unicode=True):
                    if not line or not line.strip().startswith("{"): continue
                    try:
                        chunk = json.loads(line.strip())
                        token = chunk.get("response", "")
                        done  = chunk.get("done", False)
                        if token:
                            full_response.append(token)
                            yield f"data: {json.dumps({'type':'token','content':token})}\n\n"
                            await asyncio.sleep(0)
                        if done:
                            gen_ms = round((time.time()-stream_t0)*1000, 2)
                            total  = round((time.time()-t0)*1000, 2)
                            yield f"data: {json.dumps({'type':'done','retrieval_ms':retrieval_ms,'generation_ms':gen_ms,'total_ms':total})}\n\n"
                            await asyncio.sleep(0)
                            full_text = "".join(full_response)
                            cm_add(session_id, "assistant", full_text)
                            save_message(username, session_id, "assistant", full_text)
                            break
                    except Exception: continue
            except Exception as e:
                yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"

        return StreamingResponse(
            event_stream(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    except HTTPException: raise
    except Exception as e:
        logger.error(f"[/chat] {e}")
        raise HTTPException(500, str(e))



# ══════════════════════════════════════════════════════════════════════════════
#  USE-CASE INTELLIGENCE PANELS
#  These power the 4 visible panels in the brain sidebar:
#  - Weak Areas (Interview Prep)
#  - Attempt History (Interview Prep)
#  - Roadmap (Learning Path)
#  - Gap Detection (Learning Path)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/weak-areas/{username}")
async def get_weak_areas(username: str):
    """
    Returns top weak topics with confidence levels.
    Combines: WEAK_IN edges + MISTAKE_IN edges + low decay memories.
    Powers the Weak Areas panel in Interview Prep.
    """
    try:
        areas = []
        with graph.driver.session() as session:
            # WEAK_IN edges from Gemini extraction
            r1 = session.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                      -[:MENTIONS]->(c1:Concept)-[:WEAK_IN]->(c2:Concept)
                RETURN DISTINCT c2.name AS topic, m.confidence_score AS conf,
                       m.decay_score AS freshness
                ORDER BY m.decay_score DESC LIMIT 10
            """, un=username)
            for r in r1:
                areas.append({
                    "topic": r["topic"], "type": "weak_in",
                    "confidence": round((r["conf"] or 0.5) * 100),
                    "freshness":  round((r["freshness"] or 1.0) * 100),
                    "label": "Weak Area",
                    "color": "red",
                })

            # MISTAKE_IN edges from drills
            r2 = session.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                      -[:MISTAKE_IN]->(c:Concept)
                WHERE NOT EXISTS {
                    MATCH (u)-[:REMEMBERS]->(m2:Memory)-[:CONFIRMS]->(c)
                    WHERE m2.timestamp > m.timestamp
                }
                RETURN DISTINCT c.name AS topic, m.timestamp AS when
                ORDER BY m.timestamp DESC LIMIT 8
            """, un=username)
            seen = {a["topic"] for a in areas}
            for r in r2:
                if r["topic"] not in seen:
                    areas.append({
                        "topic": r["topic"], "type": "mistake",
                        "confidence": 30,
                        "freshness":  50,
                        "label": "Past Mistake",
                        "color": "orange",
                    })
                    seen.add(r["topic"])

        return {"weak_areas": areas[:8]}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/attempt-history/{username}")
async def get_attempt_history(username: str, limit: int = 10):
    """
    Returns timeline of interview attempts: questions, outcomes, dates.
    Powers the Attempt History panel in Interview Prep.
    """
    try:
        history = []
        with graph.driver.session() as session:
            # MISTAKE_IN attempts
            r = session.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                      -[:MISTAKE_IN]->(c:Concept)
                RETURN m.content AS content, c.name AS topic,
                       toString(m.timestamp) AS when, 'mistake' AS outcome
                ORDER BY m.timestamp DESC LIMIT $limit
            """, un=username, limit=limit)
            for row in r:
                history.append({
                    "topic":    row["topic"],
                    "content":  (row["content"] or "")[:80],
                    "outcome":  "mistake",
                    "when":     row["when"] or "",
                    "icon":     "✗",
                    "color":    "red",
                })
            # CONFIRMS attempts
            r2 = session.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                      -[:CONFIRMS]->(c:Concept)
                RETURN m.content AS content, c.name AS topic,
                       toString(m.timestamp) AS when, 'confirmed' AS outcome
                ORDER BY m.timestamp DESC LIMIT $limit
            """, un=username, limit=limit)
            for row in r2:
                history.append({
                    "topic":    row["topic"],
                    "content":  (row["content"] or "")[:80],
                    "outcome":  "confirmed",
                    "when":     row["when"] or "",
                    "icon":     "✓",
                    "color":    "green",
                })

        # Sort by date desc
        history.sort(key=lambda x: x["when"], reverse=True)
        return {"history": history[:limit]}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/roadmap/{username}")
async def get_roadmap(username: str, goal: str = ""):
    """
    Returns a numbered prerequisite-aware roadmap with known/weak/unknown labels.
    Powers the Roadmap + Gap Detection panels in Learning Path Planner.
    """
    try:
        from curriculum_graph import CURRICULUM_NODES, get_curriculum_prerequisites

        # Get all requirements for goal
        actual_goal = goal or "software engineering interview"
        reqs        = await fetch_requirements(actual_goal)

        if not reqs:
            # Fall back to a broad set from curriculum
            reqs = ["arrays", "recursion", "dynamic programming",
                    "system design", "graphs", "trees", "hash tables"]

        # For each topic, determine status
        embedder  = _get_embedder()
        faiss_mgr = _get_faiss()

        confirmed_topics = set()
        weak_topics      = set()
        with graph.driver.session() as session:
            r1 = session.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                      -[:CONFIRMS]->(c:Concept)
                RETURN DISTINCT toLower(c.name) AS t
            """, un=username)
            confirmed_topics = {r["t"] for r in r1}

            r2 = session.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                      -[:MENTIONS]->(c:Concept)-[:WEAK_IN]->()
                RETURN DISTINCT toLower(c.name) AS t
            """, un=username)
            weak_topics = {r["t"] for r in r2}

            r3 = session.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                      -[:MISTAKE_IN]->(c:Concept)
                RETURN DISTINCT toLower(c.name) AS t
            """, un=username)
            for r in r3:
                weak_topics.add(r["t"])

        roadmap = []
        for i, topic in enumerate(reqs):
            tl = topic.lower()

            # Determine status
            if tl in confirmed_topics:
                status = "known"
                color  = "green"
                icon   = "✓"
            elif tl in weak_topics:
                status = "weak"
                color  = "orange"
                icon   = "⚠"
            else:
                # Check FAISS
                try:
                    vec  = embedder.embed(topic)
                    hits = faiss_mgr.search(user_id=username, query_vector=vec, top_k=1)
                    if hits and hits[0]["cosine_similarity"] >= 0.60:
                        status = "weak"
                        color  = "orange"
                        icon   = "⚠"
                    else:
                        status = "not_started"
                        color  = "dim"
                        icon   = "○"
                except Exception:
                    status = "not_started"
                    color  = "dim"
                    icon   = "○"

            # Get prerequisites from curriculum graph
            prereqs = get_curriculum_prerequisites(graph, topic, depth=1)
            prereq_names = [p["topic"] for p in prereqs[:2]]

            roadmap.append({
                "step":       i + 1,
                "topic":      topic,
                "status":     status,
                "color":      color,
                "icon":       icon,
                "prereqs":    prereq_names,
                "resource":   _get_resource(topic),
            })

        gaps = [r for r in roadmap if r["status"] == "not_started"]
        weak = [r for r in roadmap if r["status"] == "weak"]

        return {
            "roadmap":    roadmap,
            "goal":       actual_goal,
            "gaps":       [g["topic"] for g in gaps[:5]],
            "weak":       [w["topic"] for w in weak[:5]],
            "next_step":  gaps[0]["topic"] if gaps else (weak[0]["topic"] if weak else ""),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


def _get_resource(topic: str) -> str:
    """Returns a specific resource recommendation for common topics."""
    resources = {
        "dynamic programming":  "LeetCode #322 Coin Change → #300 LIS → #72 Edit Distance",
        "recursion":            "LeetCode #206 Reverse Linked List → #21 Merge Two Lists",
        "graphs":               "LeetCode #200 Number of Islands → #133 Clone Graph",
        "trees":                "LeetCode #104 Max Depth → #102 Level Order → #236 LCA",
        "binary search":        "LeetCode #704 Binary Search → #33 Search Rotated Array",
        "system design":        "Grokking System Design: URL Shortener → Rate Limiter",
        "arrays":               "LeetCode #1 Two Sum → #15 3Sum → #11 Container With Water",
        "hash tables":          "LeetCode #1 Two Sum → #49 Group Anagrams → #146 LRU Cache",
        "bfs":                  "LeetCode #102 Level Order → #127 Word Ladder",
        "dfs":                  "LeetCode #200 Islands → #130 Surrounded Regions → #417",
        "sorting algorithms":   "Implement merge sort from scratch, then quicksort",
        "linked lists":         "LeetCode #21 Merge → #206 Reverse → #141 Cycle Detection",
        "stacks":               "LeetCode #20 Valid Parens → #739 Daily Temperatures",
        "heaps":                "LeetCode #215 Kth Largest → #23 Merge K Lists",
        "backtracking":         "LeetCode #46 Permutations → #78 Subsets → #51 N-Queens",
    }
    return resources.get(topic.lower(), f"Search '{topic} interview questions LeetCode'")


@app.get("/drill/{username}")
async def get_drill_questions(username: str, count: int = 3):
    """
    Auto-generates 3-5 drill questions from the user's weak areas.
    Powers the Auto Drill Generator.
    """
    try:
        # Get weak areas
        weak_resp = await get_weak_areas(username)
        weak_areas = weak_resp.get("weak_areas", [])

        if not weak_areas:
            return {
                "questions": [
                    {"topic": "general", "question": "Explain the difference between BFS and DFS. When would you use each?", "difficulty": "medium"},
                    {"topic": "general", "question": "What is the time complexity of searching in a hash table? What causes collisions?", "difficulty": "easy"},
                    {"topic": "general", "question": "Design a stack that supports push, pop, and getMin in O(1) time.", "difficulty": "medium"},
                ],
                "source": "general"
            }

        drill_templates = {
            "dynamic programming": [
                "Solve the coin change problem: given coins [1,5,10] and amount=27, find minimum coins.",
                "What is the difference between memoization and tabulation in DP?",
                "Solve Longest Common Subsequence for 'ABCBDAB' and 'BDCABA'.",
            ],
            "recursion": [
                "Write a recursive function to find all permutations of [1,2,3].",
                "Explain the call stack for fibonacci(4). What is the time complexity?",
                "Write a recursive binary search. What is its space complexity?",
            ],
            "graphs": [
                "Given an undirected graph, detect if it contains a cycle. Walk through your approach.",
                "Explain Dijkstra's algorithm. What data structure does it use and why?",
                "Find the shortest path in an unweighted graph using BFS.",
            ],
            "system design": [
                "Design a URL shortener like bit.ly. What are the key components?",
                "How would you design a rate limiter for an API with 10M requests/day?",
                "Design a distributed cache. How do you handle cache invalidation?",
            ],
            "trees": [
                "Write an in-order traversal of a BST without recursion.",
                "Find the lowest common ancestor of two nodes in a binary tree.",
                "Given a sorted array, construct a balanced BST.",
            ],
            "arrays": [
                "Find the maximum subarray sum (Kadane's algorithm). Trace through [-2,1,-3,4,-1,2,1,-5,4].",
                "Given a sorted array rotated at some pivot, find a target element.",
                "Move all zeros to the end of an array in-place.",
            ],
        }

        questions = []
        used_topics = set()
        for area in weak_areas[:count]:
            topic = area["topic"].lower()
            if topic in used_topics:
                continue
            used_topics.add(topic)

            # Find best matching template
            matched = None
            for key, qs in drill_templates.items():
                if key in topic or topic in key:
                    matched = qs
                    break

            if matched:
                q = matched[len(questions) % len(matched)]
                questions.append({
                    "topic":      area["topic"],
                    "question":   q,
                    "difficulty": "hard" if area["confidence"] < 40 else "medium",
                    "label":      area["label"],
                })
            else:
                questions.append({
                    "topic":    area["topic"],
                    "question": f"Explain {area['topic']} and walk me through a common interview problem that uses it.",
                    "difficulty": "medium",
                    "label":    area["label"],
                })

            if len(questions) >= count:
                break

        return {"questions": questions[:count], "source": "personalized"}
    except Exception as e:
        raise HTTPException(500, str(e))

# ══════════════════════════════════════════════════════════════════════════════
#  GRAPH / RECALL / STATS / MINDMAP
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/memory/mindmap")
async def get_mindmap(username: str = Depends(_verify_token)):
    try:
        data = graph.get_visual_graph(username)
        return {"nodes": data["nodes"], "edges": data["links"],
                "metadata": {"username": username, "node_count": len(data["nodes"])}}
    except Exception as e: raise HTTPException(500, str(e))

@app.get("/graph-visuals/{username}")
def get_graph_visuals(username: str):
    try: return graph.get_visual_graph(username)
    except Exception as e: raise HTTPException(500, str(e))

@app.get("/recall/{username}")
async def recall_memories(username: str):
    try:
        visual_data  = graph.get_visual_graph(username)
        memory_count = len([n for n in visual_data["nodes"] if n["type"] == "Memory"])
        return {"memory_count": memory_count, "graph_data": visual_data}
    except Exception as e: raise HTTPException(500, str(e))

@app.get("/stats/{username}")
async def get_stats(username: str):
    try:
        visual_data   = graph.get_visual_graph(username)
        memory_count  = len([n for n in visual_data["nodes"] if n["type"] == "Memory"])
        concept_count = len([n for n in visual_data["nodes"] if n["type"] == "Concept"])
        return {
            "memory_count": memory_count, "concept_count": concept_count,
            "edge_count": len(visual_data["links"]), "node_count": len(visual_data["nodes"]),
        }
    except Exception as e: raise HTTPException(500, str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)