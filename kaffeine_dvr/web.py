"""
Lightweight, dependency-free HTTP Server & Remote Web Companion for Kaffeine DVR.

Provides:
- Mobile & tablet-friendly web interface for TV Guide browsing and scheduling.
- Active Schedule & Completed Recordings management.
- Video streaming with RFC 7233 HTTP Range header chunking for instant HTML5 scrubbing.
- Salted SHA-256 session token authentication for Tailscale / LAN access.
"""

import http.cookies
import http.server
import json
import math
import mimetypes
import secrets
import shutil
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import ConfigManager
from .guide_service import GuideService
from .queue_manager import QueueManager
from .storage_manager import StorageManager
from .web_ui import WEB_HTML_TEMPLATE

_CACHED_FAVICON_BYTES: Optional[bytes] = None
MAX_POST_BODY_BYTES = 1024 * 1024  # 1 MB cap for JSON API bodies
MAX_ACTIVE_TOKENS = 128
SESSION_COOKIE_NAME = "kaffeine_session"


def _is_loopback_addr(addr: str) -> bool:
    """Returns True if addr is a loopback address or hostname."""
    val = (addr or "").strip().lower()
    return val in ("127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost")


def _get_favicon_bytes() -> bytes:
    global _CACHED_FAVICON_BYTES
    if _CACHED_FAVICON_BYTES is not None:
        return _CACHED_FAVICON_BYTES

    base_dir = Path(__file__).resolve().parent.parent
    candidates = [
        base_dir / "assets" / "icons" / "kaffeine-dvr-32.png",
        base_dir / "assets" / "icons" / "kaffeine-dvr-64.png",
        base_dir / "assets" / "kaffeine-dvr.png",
    ]
    if hasattr(sys, "_MEIPASS"):
        meipass = Path(getattr(sys, "_MEIPASS"))
        candidates.insert(0, meipass / "assets" / "icons" / "kaffeine-dvr-32.png")
        candidates.insert(1, meipass / "assets" / "kaffeine-dvr.png")

    for cand in candidates:
        if cand.is_file():
            try:
                _CACHED_FAVICON_BYTES = cand.read_bytes()
                return _CACHED_FAVICON_BYTES
            except Exception:
                pass

    _CACHED_FAVICON_BYTES = b""
    return _CACHED_FAVICON_BYTES


class KaffeineWebRequestHandler(http.server.BaseHTTPRequestHandler):
    """Handles HTTP requests for Kaffeine DVR Web Companion."""

    server_version = "KaffeineDVR-Web/1.0"

    @property
    def server_obj(self) -> Optional["KaffeineWebServer"]:
        """Returns the owner KaffeineWebServer instance."""
        return getattr(self.server, "owner", None)

    def log_message(self, fmt, *args):
        """Silences default HTTP request console logging to keep terminal output clean."""
        pass

    def _send_security_headers(self, include_csp: bool = False):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if include_csp:
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; media-src 'self' blob:; "
                "img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
            )

    def _send_json(self, data: Any, status: int = 200, extra_headers: Optional[List[Tuple[str, str]]] = None):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self._send_security_headers()
        if extra_headers:
            for hk, hv in extra_headers:
                safe_hk = str(hk).replace("\r", "").replace("\n", "")
                safe_hv = str(hv).replace("\r", "").replace("\n", "")
                self.send_header(safe_hk, safe_hv)
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_text: str, status: int = 200):
        body = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self._send_security_headers(include_csp=True)
        self.end_headers()
        self.wfile.write(body)

    def _extract_request_token(self) -> str:
        # 1. Bearer Token in Authorization header
        auth_hdr = self.headers.get("Authorization", "")
        if auth_hdr.startswith("Bearer "):
            tok = auth_hdr[7:].strip()
            if tok:
                return tok

        # 2. HttpOnly Session Cookie
        cookie_hdr = self.headers.get("Cookie", "")
        if cookie_hdr:
            try:
                cookie = http.cookies.SimpleCookie()
                cookie.load(cookie_hdr)
                if SESSION_COOKIE_NAME in cookie and cookie[SESSION_COOKIE_NAME].value:
                    return cookie[SESSION_COOKIE_NAME].value.strip()
            except Exception:
                pass

        # 3. Token in Query Parameter (fallback for legacy direct URLs)
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        return (qs.get("token", [""])[0] or "").strip()

    def _is_authenticated(self) -> bool:
        if not self.server_obj:
            return False
        if not self.server_obj.config_mgr.has_web_password:
            # Fail closed unless strictly bound to loopback and accessed locally
            client_ip = self.client_address[0] if self.client_address else ""
            return _is_loopback_addr(self.server_obj.bind_addr) and _is_loopback_addr(client_ip)

        token = self._extract_request_token()
        return bool(token and self.server_obj.is_valid_token(token))

    def _is_same_origin(self) -> bool:
        """Blocks cross-origin browser CSRF requests when an Origin header is supplied."""
        origin = (self.headers.get("Origin") or "").strip()
        if not origin:
            return True
        host = (self.headers.get("Host") or "").strip().lower()
        if not host:
            return False
        try:
            parsed_origin = urllib.parse.urlparse(origin)
            return parsed_origin.netloc.lower() == host
        except Exception:
            return False

    def _is_within_recording_folder(self, target_path: Path) -> bool:
        """Verifies target_path resolves strictly inside the configured recording folder."""
        if not self.server_obj:
            return False
        try:
            rec_folder = self.server_obj.storage_mgr.get_recording_folder().resolve()
            resolved_target = target_path.resolve()
            return resolved_target.is_relative_to(rec_folder)
        except Exception:
            return False

    def do_POST(self):
        """Dispatches POST API requests including authentication, recording creation, and tuning."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if not self._is_same_origin():
            self._send_json({"error": "Forbidden cross-origin request"}, status=403)
            return

        raw_len = self.headers.get("Content-Length")
        try:
            content_len = int(raw_len) if raw_len is not None else 0
        except (ValueError, TypeError):
            self._send_json({"error": "Invalid Content-Length header"}, status=400)
            return

        if content_len < 0:
            self._send_json({"error": "Invalid Content-Length header"}, status=400)
            return
        if content_len > MAX_POST_BODY_BYTES:
            self._send_json({"error": "Request body too large"}, status=413)
            return

        try:
            body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else ""
        except UnicodeDecodeError:
            self._send_json({"error": "Invalid UTF-8 request body"}, status=400)
            return

        # Login endpoint: POST /api/login
        if path == "/api/login":
            client_ip = self.client_address[0] if self.client_address else "127.0.0.1"
            # Check lockout
            is_locked, remaining_sec = self.server_obj.check_rate_limit(client_ip)
            if is_locked:
                self._send_json({
                    "error": f"Too many incorrect attempts. Please wait {remaining_sec} seconds before trying again.",
                    "locked": True,
                    "retry_after": remaining_sec
                }, status=429)
                return

            try:
                data = json.loads(body) if body else {}
                pw = data.get("password", "")
                if self.server_obj.config_mgr.verify_web_password(pw):
                    self.server_obj.record_successful_login(client_ip)
                    token = self.server_obj.create_session_token()
                    cookie_hdr = f"{SESSION_COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=604800"
                    self._send_json(
                        {"token": token, "status": "ok"},
                        extra_headers=[("Set-Cookie", cookie_hdr)],
                    )
                    return

                # Incorrect password: record attempt and apply anti-brute delay (5 attempts max, 15 min lockout)
                remaining_attempts, lockout_sec = self.server_obj.record_failed_login(client_ip, max_attempts=5, lockout_duration=900)
                time.sleep(0.5)

                if lockout_sec > 0:
                    self._send_json({
                        "error": f"Too many incorrect attempts. Access locked for {lockout_sec // 60} minutes.",
                        "locked": True,
                        "retry_after": lockout_sec
                    }, status=429)
                else:
                    self._send_json({
                        "error": f"Invalid password. {remaining_attempts} attempts remaining.",
                        "remaining_attempts": remaining_attempts
                    }, status=401)
                return
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
                return

        if path == "/api/logout":
            token = self._extract_request_token()
            if token and self.server_obj:
                self.server_obj.revoke_session_token(token)
            clear_cookie = f"{SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
            self._send_json({"status": "logged_out"}, extra_headers=[("Set-Cookie", clear_cookie)])
            return

        # Enforce authentication for all other mutating endpoints
        if not self._is_authenticated():
            self._send_json({"error": "Unauthorized"}, status=401)
            return

        # Schedule show: POST /api/schedule
        if path == "/api/schedule":
            try:
                data = json.loads(body)
                title = data.get("title", "").strip()
                ch = data.get("channel", "").strip()
                start_iso = data.get("start_iso", "").strip()
                dur_iso = data.get("duration_iso", "00:30:00").strip()

                if not title or not ch or not start_iso:
                    self._send_json({"error": "Missing required fields"}, status=400)
                    return

                qid = self.server_obj.queue_mgr.add_recording(
                    title=title,
                    channel=ch,
                    start_iso=start_iso,
                    duration_iso=dur_iso
                )
                self.server_obj.notify_queue_changed()
                self._send_json({"id": qid, "status": "scheduled"})
                return
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
                return

        # Start live timeshift session: POST /api/timeshift/start
        if path == "/api/timeshift/start":
            try:
                data = json.loads(body) if body else {}
                title = data.get("title", "Live TV").strip()
                ch = data.get("channel", "").strip()
                start_iso = data.get("start_iso", "").strip()
                dur_iso = data.get("duration_iso", "02:00:00").strip()

                if not ch:
                    self._send_json({"error": "Missing channel parameter"}, status=400)
                    return

                now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
                if not start_iso:
                    start_iso = now_iso

                # Check tuner availability
                active_queue = self.server_obj.queue_mgr.list_queue(include_completed=False)
                conflicting = []
                for r in active_queue:
                    if r.get("is_timeshift"):
                        continue
                    if r.get("status") in ("RECORDING", "ARMED", "DISPATCHED"):
                        r_ch = (r.get("channel") or "").strip().lower()
                        if r_ch != ch.lower():
                            conflicting.append(r)

                total_tuners = self.server_obj.config_mgr.get_effective_tuner_count()
                if len(conflicting) >= total_tuners:
                    c_names = ", ".join([f"'{c.get('title')}' ({c.get('channel')})" for c in conflicting])
                    self._send_json({
                        "error": f"All TV tuners ({total_tuners}) are currently in use recording on other channels: {c_names}. Stop conflicting recordings before starting timeshift.",
                        "tuner_busy": True
                    }, status=409)
                    return

                # Check if this show is already actively recording in queue
                active_map = self.server_obj.queue_mgr.get_active_scheduled_map()
                ch_key = ch.strip().lower()
                iso_key = start_iso[:16]
                rec_info = active_map.get((ch_key, iso_key))

                if rec_info and rec_info.get("status") == "RECORDING":
                    qid = rec_info.get("id")
                    stream_url = f"/api/stream/active/{qid}"
                    self._send_json({
                        "status": "ok",
                        "queue_id": qid,
                        "stream_url": stream_url,
                        "is_scheduled": True
                    })
                    return

                # Add timeshift entry to queue
                qid = self.server_obj.queue_mgr.add_recording(
                    title=title,
                    channel=ch,
                    start_iso=start_iso,
                    duration_iso=dur_iso,
                    lead_time_mins=0,
                    buffer_mins=0,
                    is_timeshift=True
                )

                # Dispatch recording to Kaffeine
                if self.server_obj.watcher:
                    self.server_obj.watcher.check_and_dispatch(notify=False)
                elif self.server_obj.dbus_client:
                    self.server_obj.dbus_client.schedule_recording(
                        channel=ch,
                        name=title,
                        start_iso=start_iso,
                        duration_iso=dur_iso
                    )

                # Register in active timeshift sessions
                self.server_obj.active_timeshift_sessions[qid] = {
                    "queue_id": qid,
                    "channel": ch,
                    "title": title,
                    "start_time": time.time(),
                    "file_path": None
                }

                # Brief wait for initial buffer
                time.sleep(2.0)

                stream_url = f"/api/stream/active/{qid}"
                self.server_obj.notify_queue_changed()
                self._send_json({
                    "status": "ok",
                    "queue_id": qid,
                    "stream_url": stream_url,
                    "is_scheduled": False
                })
                return
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
                return

        # Stop live timeshift session: POST /api/timeshift/stop
        if path == "/api/timeshift/stop":
            try:
                data = json.loads(body) if body else {}
                qid = data.get("queue_id")
                if not qid:
                    self._send_json({"error": "Missing queue_id parameter"}, status=400)
                    return

                qid = int(qid)
                rec = self.server_obj.queue_mgr.get_recording(qid)
                is_tracked_ts = qid in self.server_obj.active_timeshift_sessions
                if not rec and not is_tracked_ts:
                    self._send_json({"error": "Timeshift session not found"}, status=404)
                    return
                if rec and not bool(rec.get("is_timeshift")) and not is_tracked_ts:
                    self._send_json({"error": "Target recording is not a timeshift session"}, status=403)
                    return

                ts_session = self.server_obj.active_timeshift_sessions.pop(qid, None)

                # Stop recording in Kaffeine and remove from queue
                self.server_obj.queue_mgr.remove_recording(qid, dbus_client=self.server_obj.dbus_client)
                if self.server_obj.dbus_client and rec:
                    self.server_obj.dbus_client.cancel_recording(
                        key=rec.get("kaffeine_key"),
                        channel=rec.get("channel"),
                        title=rec.get("title")
                    )

                # Clean up temporary timeshift file if configured and safely within recording folder
                if getattr(self.server_obj.config_mgr, "delete_timeshift_on_exit", True) and not (rec and rec.get("protected")):
                    fpath = (rec.get("file_path") if rec else None) or (ts_session.get("file_path") if ts_session else None)
                    if fpath:
                        try:
                            p = Path(fpath).resolve()
                            if p.exists() and self._is_within_recording_folder(p):
                                p.unlink()
                        except Exception:
                            pass

                self.server_obj.notify_queue_changed()
                self._send_json({"status": "stopped", "queue_id": qid})
                return
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
                return

        self._send_json({"error": "Not Found"}, status=404)

    def do_DELETE(self):
        """Dispatches DELETE API requests to cancel scheduled or active recordings."""
        if not self._is_same_origin():
            self._send_json({"error": "Forbidden cross-origin request"}, status=403)
            return
        if not self._is_authenticated():
            self._send_json({"error": "Unauthorized"}, status=401)
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Cancel schedule or active recording: DELETE /api/schedule/<id>
        if path.startswith("/api/schedule/"):
            try:
                qid = int(path.split("/")[-1])
                rec_info = self.server_obj.queue_mgr.cancel_recording(qid, dbus_client=self.server_obj.dbus_client)
                self.server_obj.active_timeshift_sessions.pop(qid, None)
                self.server_obj.notify_queue_changed()
                status_res = "completed" if (rec_info and rec_info.get("stopped_in_progress")) else "cancelled"
                self._send_json({"status": status_res, "id": qid})
                return
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
                return

        self._send_json({"error": "Not Found"}, status=404)

    def do_GET(self):
        """Dispatches GET API and static web asset requests."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Root route: Serve frontend SPA HTML
        if path in ("/", "/index.html"):
            self._send_html(WEB_HTML_TEMPLATE)
            return

        # Favicon routes (unauthenticated)
        if path in ("/favicon.ico", "/favicon.png"):
            fav_bytes = _get_favicon_bytes()
            if fav_bytes:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(fav_bytes)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(fav_bytes)
                return
            else:
                self._send_json({"error": "Favicon not found"}, status=404)
                return

        # All API endpoints require authentication (except status probe which returns 401 if unauthed)
        if path.startswith("/api/"):
            if not self._is_authenticated():
                self._send_json({"error": "Unauthorized"}, status=401)
                return

        # System status: GET /api/status
        if path == "/api/status":
            try:
                active_recs = len(self.server_obj.queue_mgr.list_queue())
                folder = self.server_obj.storage_mgr.get_recording_folder()
                free_gb = 0
                if folder and folder.exists():
                    _, _, free = shutil.disk_usage(str(folder))
                    free_gb = round(free / (1024 ** 3), 1)
                extra_hdrs = None
                auth_hdr = self.headers.get("Authorization", "")
                if (
                    self.server_obj.config_mgr.has_web_password
                    and auth_hdr.startswith("Bearer ")
                    and SESSION_COOKIE_NAME not in self.headers.get("Cookie", "")
                ):
                    tok = auth_hdr[7:].strip()
                    canonical_tok = self.server_obj.get_valid_token(tok)
                    if canonical_tok:
                        safe_tok = canonical_tok.replace("\r", "").replace("\n", "")
                        extra_hdrs = [("Set-Cookie", f"{SESSION_COOKIE_NAME}={safe_tok}; Path=/; HttpOnly; SameSite=Strict; Max-Age=604800")]
                self._send_json({
                    "status": "online",
                    "free_disk_gb": free_gb,
                    "active_recordings": active_recs,
                    "server_port": self.server_obj.port
                }, extra_headers=extra_hdrs)
                return
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
                return

        # TV Guide listings: GET /api/guide?date=YYYY-MM-DD&trim=0|1
        if path == "/api/guide":
            try:
                qs = urllib.parse.parse_qs(parsed.query)
                target_date = qs.get("date", [""])[0] or time.strftime("%Y-%m-%d")
                trim_param = qs.get("trim", ["0"])[0]
                trim_ended = trim_param == "1"
                programs = self.server_obj.guide_svc.search_programs(
                    airdate=target_date,
                    trim_ended=trim_ended,
                    include_overhang=True
                )

                # Cross-reference with scheduled map
                scheduled_map = self.server_obj.queue_mgr.get_active_scheduled_map()

                out = []
                for p in programs:
                    ch_name = p.get("kaffeine_channel") or p.get("channel") or ""
                    ch_key = ch_name.strip().lower()
                    iso_key = (p.get("start_iso") or "")[:16]
                    rec_info = scheduled_map.get((ch_key, iso_key))
                    is_sched = rec_info is not None
                    rec_status = rec_info.get("status", "") if rec_info else ""
                    is_recording = (rec_status == "RECORDING")
                    queue_id = rec_info.get("id") if rec_info else None
                    dur_iso = p.get("duration_iso") or "00:30:00"
                    rt_mins = p.get("runtime_mins")
                    if not rt_mins:
                        try:
                            dparts = [int(x) for x in dur_iso.split(":")]
                            rt_mins = dparts[0] * 60 + dparts[1]
                        except Exception:
                            rt_mins = 30
                    out.append({
                        "id": p.get("id"),
                        "queue_id": queue_id,
                        "title": p.get("show_title") or p.get("title") or "Untitled",
                        "episode_title": p.get("episode_title") or "",
                        "channel": ch_name,
                        "start_iso": p.get("start_iso"),
                        "duration_iso": dur_iso,
                        "runtime_mins": rt_mins,
                        "summary": p.get("summary") or "",
                        "category": p.get("_category") or "",
                        "is_scheduled": is_sched,
                        "is_recording": is_recording,
                        "rec_status": rec_status
                    })
                self._send_json(out)
                return
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
                return

        # Recordings list: GET /api/recordings
        if path == "/api/recordings":
            try:
                active = self.server_obj.queue_mgr.list_queue()
                hist = self.server_obj.queue_mgr.list_history()

                active_out = []
                for a in active:
                    aid = a.get("id")
                    st = a.get("status")
                    stream_url = f"/api/stream/active/{aid}" if (st == "RECORDING" and aid) else ""
                    active_out.append({
                        "id": aid,
                        "title": a.get("title"),
                        "channel": a.get("channel"),
                        "start_iso": a.get("start_iso"),
                        "duration_iso": a.get("duration_iso"),
                        "status": st,
                        "is_timeshift": bool(a.get("is_timeshift")),
                        "file_available": bool(stream_url),
                        "stream_url": stream_url
                    })

                hist_out = []
                for h in hist:
                    hid = h.get("id")
                    is_avail, found, sz_bytes = self.server_obj.storage_mgr.check_history_file_availability(h)
                    size_str = f"{round(sz_bytes / (1024 ** 3), 2)} GB" if sz_bytes > 0 else ""
                    filename = found.name if (is_avail and found) else ""
                    stream_url = ""
                    if is_avail and hid is not None:
                        if filename:
                            stream_url = f"/api/stream/{hid}/{urllib.parse.quote(filename)}"
                        else:
                            stream_url = f"/api/stream/{hid}"
                    hist_out.append({
                        "id": hid,
                        "title": h.get("title"),
                        "filename": filename,
                        "channel": h.get("channel"),
                        "start_iso": h.get("start_iso"),
                        "completed_at": h.get("completed_at"),
                        "duration_iso": h.get("duration_iso"),
                        "status": "COMPLETED",
                        "size_str": size_str,
                        "file_available": is_avail,
                        "stream_url": stream_url
                    })

                self._send_json({"active": active_out, "history": hist_out})
                return
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
                return

        # Stream active in-progress or timeshift recording: GET /api/stream/active/<qid>
        if path.startswith("/api/stream/active/"):
            try:
                subpath = path[len("/api/stream/active/"):].strip("/")
                qid_str = subpath.split("/")[0]
                qid = int(qid_str)

                rec = self.server_obj.queue_mgr.get_recording(qid)
                if not rec:
                    self._send_json({"error": "Active recording not found in queue"}, status=404)
                    return

                title = rec.get("title", "")
                fpath_str = rec.get("file_path")
                active_file = Path(fpath_str) if fpath_str else None

                if not active_file or not active_file.exists():
                    active_file = self.server_obj.storage_mgr.find_active_or_recent_recording_file(
                        title, max_age_seconds=14400, min_size_bytes=1024
                    )

                if not active_file or not active_file.exists():
                    # Check recording folder for newest modified video file
                    rec_folder = self.server_obj.storage_mgr.get_recording_folder()
                    if rec_folder and rec_folder.exists():
                        newest_f = None
                        newest_m = 0
                        for vf in rec_folder.iterdir():
                            if vf.is_file() and vf.suffix.lower() in StorageManager.VIDEO_EXTENSIONS:
                                try:
                                    st = vf.stat()
                                    if st.st_size > 1024 and st.st_mtime > newest_m:
                                        newest_m = st.st_mtime
                                        newest_f = vf
                                except Exception:
                                    pass
                        if newest_f and (time.time() - newest_m) < 600:
                            active_file = newest_f

                if not active_file or not active_file.exists():
                    self._send_json({"error": "Live stream file not yet created or buffered on disk"}, status=404)
                    return

                resolved_active = active_file.resolve()
                if not self._is_within_recording_folder(resolved_active):
                    self._send_json({"error": "Access denied"}, status=403)
                    return

                # Cache file path in timeshift session if applicable
                if qid in self.server_obj.active_timeshift_sessions:
                    self.server_obj.active_timeshift_sessions[qid]["file_path"] = str(resolved_active)

                # Stream with live follow mode enabled
                self._stream_file(resolved_active, parsed.query, is_live=True)
                return
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
                return

        # Stream recording with RFC 7233 byte-range support: GET /api/stream/<id> or /api/stream/<id>/<filename>
        if path.startswith("/api/stream/"):
            try:
                subpath = path[len("/api/stream/"):].strip("/")
                hid_str = subpath.split("/")[0]
                hid = int(hid_str)
                import sqlite3
                conn = self.server_obj.queue_mgr._get_connection()
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("SELECT * FROM recording_history WHERE id = ?", (hid,))
                row = cur.fetchone()
                conn.close()

                if not row:
                    self._send_json({"error": "Recording not found"}, status=404)
                    return

                h_dict = dict(row)
                is_avail, found, _ = self.server_obj.storage_mgr.check_history_file_availability(h_dict)
                if not is_avail or not found or not found.exists():
                    self._send_json({"error": "Video file not found on disk"}, status=404)
                    return

                # Security check: Ensure file resides strictly inside recording folder
                resolved_target = found.resolve()
                if not self._is_within_recording_folder(resolved_target):
                    self._send_json({"error": "Access denied"}, status=403)
                    return

                self._stream_file(resolved_target, parsed.query, is_live=False)
                return
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
                return

        self._send_json({"error": "Not Found"}, status=404)

    def _stream_file(self, file_path: Path, query_str: str = "", is_live: bool = False):
        """Streams media file. If MPEG-2 TS (.m2t), transcodes on-the-fly to MP4 for browser compatibility."""
        qs = urllib.parse.parse_qs(query_str)
        is_raw_download = qs.get("raw", ["0"])[0] == "1"

        # If already mp4 or webm, or raw download requested, use standard Range streaming
        if not is_live and (is_raw_download or file_path.suffix.lower() in (".mp4", ".m4v", ".webm")):
            self._stream_file_with_range(file_path, is_download=is_raw_download)
            return

        # Check if ffmpeg is available on system
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            self._stream_file_with_range(file_path, is_download=False)
            return

        try:
            start_time_sec = float(qs.get("t", ["0"])[0])
            if not math.isfinite(start_time_sec) or start_time_sec < 0:
                start_time_sec = 0.0
        except (ValueError, TypeError):
            start_time_sec = 0.0

        stream_filename = file_path.with_suffix(".mp4").name
        quoted_stream_fn = urllib.parse.quote(stream_filename, safe="")
        ascii_stream_fn = stream_filename.encode("ascii", "ignore").decode("ascii").replace('"', "") or "stream.mp4"
        cd_header = f'inline; filename="{ascii_stream_fn}"; filename*=UTF-8\'\'{quoted_stream_fn}'

        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Disposition", cd_header)
        self.send_header("Cache-Control", "no-cache")
        self._send_security_headers()
        self.end_headers()

        import subprocess
        cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel", "error",
        ]
        if is_live:
            cmd.extend(["-follow", "1"])
        if start_time_sec > 0:
            cmd.extend(["-ss", str(start_time_sec)])

        cmd.extend([
            "-i", str(file_path),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "-f", "mp4",
            "-"
        ])

        try:
            with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
                if proc.stdout:
                    while True:
                        chunk = proc.stdout.read(64 * 1024)
                        if not chunk:
                            break
                        try:
                            self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError):
                            proc.kill()
                            break
        except Exception:
            pass

    def _stream_file_with_range(self, file_path: Path, is_download: bool = False):
        """Streams a media file supporting HTTP Range headers for seeking/scrubbing."""
        total_size = file_path.stat().st_size
        range_header = self.headers.get("Range")

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "video/mp2t" if file_path.suffix.lower() in (".m2t", ".ts") else "video/mp4"

        start = 0
        end = total_size - 1
        has_valid_range = False

        if range_header:
            if not range_header.startswith("bytes="):
                self._send_json({"error": "Invalid Range header"}, status=416)
                return
            range_spec = range_header[6:].split(",")[0].strip()
            parts = range_spec.split("-")
            if len(parts) != 2:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{total_size}")
                self.end_headers()
                return
            try:
                if not parts[0] and parts[1]:
                    # Suffix range: bytes=-N
                    suffix_len = int(parts[1])
                    if suffix_len <= 0 or total_size == 0:
                        raise ValueError("Invalid suffix length")
                    start = max(0, total_size - suffix_len)
                    end = total_size - 1
                elif parts[0]:
                    start = int(parts[0])
                    end = int(parts[1]) if parts[1] else (total_size - 1)
                else:
                    raise ValueError("Empty range bounds")
                has_valid_range = True
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{total_size}")
                self.end_headers()
                return

        if total_size == 0 and not has_valid_range:
            start = 0
            end = -1
        elif start < 0 or start >= total_size or end < start:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{total_size}")
            self.end_headers()
            return

        end = min(end, total_size - 1) if total_size > 0 else -1
        chunk_len = max(0, end - start + 1) if total_size > 0 else 0

        filename = file_path.name
        quoted_filename = urllib.parse.quote(filename, safe="")
        ascii_filename = filename.encode("ascii", "ignore").decode("ascii").replace('"', "") or "recording.m2t"
        disposition_type = "attachment" if is_download else "inline"
        content_disposition = f'{disposition_type}; filename="{ascii_filename}"; filename*=UTF-8\'\'{quoted_filename}'

        if has_valid_range:
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{total_size}")
        else:
            self.send_response(200)

        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(chunk_len))
        self.send_header("Content-Disposition", content_disposition)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        self._send_security_headers()
        self.end_headers()

        # Stream chunk
        chunk_size = 64 * 1024
        with open(file_path, "rb") as f:
            f.seek(start)
            bytes_left = chunk_len
            while bytes_left > 0:
                read_sz = min(chunk_size, bytes_left)
                data = f.read(read_sz)
                if not data:
                    break
                try:
                    self.wfile.write(data)
                    bytes_left -= len(data)
                except (BrokenPipeError, ConnectionResetError):
                    break


class ThreadedHTTPServer(http.server.ThreadingHTTPServer):
    """Threading HTTPServer with immediate address reuse and owner reference."""
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass, owner: "KaffeineWebServer"):
        """Initializes threaded HTTP server and associates owner reference."""
        self.owner = owner
        super().__init__(server_address, RequestHandlerClass)


class KaffeineWebServer:
    """Manages the background HTTP web server thread and active sessions."""

    def __init__(
        self,
        config_mgr: ConfigManager,
        queue_mgr: QueueManager,
        guide_svc: GuideService,
        storage_mgr: StorageManager,
        dbus_client: Optional[Any] = None,
        watcher: Optional[Any] = None,
        on_queue_changed: Optional[Any] = None
    ):
        """Initializes web server instance with application managers and bind settings."""
        self.config_mgr = config_mgr
        self.queue_mgr = queue_mgr
        self.guide_svc = guide_svc
        self.storage_mgr = storage_mgr
        self.dbus_client = dbus_client
        self.watcher = watcher
        self.on_queue_changed = on_queue_changed

        self.port = self.config_mgr.web_server_port
        self.bind_addr = self.config_mgr.web_server_bind
        self.server: Optional[ThreadedHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.active_tokens: Dict[str, float] = {}
        self.failed_attempts: Dict[str, list] = {}  # ip -> list of timestamps
        self.lockouts: Dict[str, float] = {}        # ip -> lockout until timestamp
        self.active_timeshift_sessions: Dict[int, Dict[str, Any]] = {} # qid -> session info
        self._lock = threading.Lock()

    def notify_queue_changed(self):
        """Invoke external queue changed callback if configured."""
        if callable(self.on_queue_changed):
            try:
                self.on_queue_changed()
            except Exception as e:
                print(f"Error in on_queue_changed callback: {e}")

    def _prune_auth_state_locked(self, now: float):
        """Prunes expired tokens, stale failed login records, and expired lockouts (caller holds self._lock)."""
        expired_toks = [t for t, exp in self.active_tokens.items() if now >= exp]
        for t in expired_toks:
            del self.active_tokens[t]

        expired_locks = [ip for ip, until in self.lockouts.items() if now >= until]
        for ip in expired_locks:
            del self.lockouts[ip]

        stale_ips = []
        for ip, ts_list in self.failed_attempts.items():
            recent = [t for t in ts_list if now - t < 900]
            if recent:
                self.failed_attempts[ip] = recent
            else:
                stale_ips.append(ip)
        for ip in stale_ips:
            del self.failed_attempts[ip]

    def check_rate_limit(self, client_ip: str) -> tuple[bool, int]:
        """
        Check if client_ip is currently locked out from login attempts.
        Returns (is_locked, remaining_seconds).
        """
        now = time.time()
        with self._lock:
            self._prune_auth_state_locked(now)
            lockout_until = self.lockouts.get(client_ip, 0)
            if now < lockout_until:
                return True, int(lockout_until - now) + 1
            return False, 0

    def record_failed_login(self, client_ip: str, max_attempts: int = 5, lockout_duration: int = 900) -> tuple[int, int]:
        """
        Record a failed login attempt for client_ip.
        If failed attempts exceed max_attempts, locks out the IP for lockout_duration (default 15 mins).
        Returns (remaining_attempts_allowed, lockout_seconds_if_locked).
        """
        now = time.time()
        with self._lock:
            self._prune_auth_state_locked(now)
            attempts = [t for t in self.failed_attempts.get(client_ip, []) if now - t < 900]
            attempts.append(now)
            self.failed_attempts[client_ip] = attempts

            if len(attempts) >= max_attempts:
                lockout_until = now + lockout_duration
                self.lockouts[client_ip] = lockout_until
                self.failed_attempts.pop(client_ip, None)
                return 0, lockout_duration
            return max(0, max_attempts - len(attempts)), 0

    def record_successful_login(self, client_ip: str):
        """Reset failed attempt counters upon successful authentication."""
        with self._lock:
            self.failed_attempts.pop(client_ip, None)
            self.lockouts.pop(client_ip, None)

    def create_session_token(self) -> str:
        """Generates a secure random 7-day authentication session token."""
        now = time.time()
        with self._lock:
            self._prune_auth_state_locked(now)
            if len(self.active_tokens) >= MAX_ACTIVE_TOKENS:
                # Evict oldest-expiring tokens to keep memory bounded
                oldest = sorted(self.active_tokens.items(), key=lambda kv: kv[1])
                for old_tok, _ in oldest[: len(self.active_tokens) - MAX_ACTIVE_TOKENS + 1]:
                    del self.active_tokens[old_tok]
            token = secrets.token_hex(24)
            self.active_tokens[token] = now + (7 * 86400)
            return token

    def revoke_session_token(self, token: str):
        """Revokes an active session token immediately."""
        if not token:
            return
        with self._lock:
            self.active_tokens.pop(token, None)

    def get_valid_token(self, token: str) -> Optional[str]:
        """Returns the stored server-side session token if active and unexpired."""
        if not token:
            return None
        now = time.time()
        with self._lock:
            for stored_tok in list(self.active_tokens.keys()):
                if secrets.compare_digest(stored_tok, token):
                    exp = self.active_tokens.get(stored_tok, 0.0)
                    if now < exp:
                        return stored_tok
                    del self.active_tokens[stored_tok]
                    return None
            return None

    def is_valid_token(self, token: str) -> bool:
        """Validates that a session token is active and unexpired."""
        return self.get_valid_token(token) is not None

    def is_running(self) -> bool:
        """Returns True if the background web server thread is currently executing."""
        return self.server is not None and self.thread is not None and self.thread.is_alive()

    def start(self) -> bool:
        """Starts the background web server thread."""
        if self.is_running():
            return True

        self.port = self.config_mgr.web_server_port
        self.bind_addr = self.config_mgr.web_server_bind

        try:
            addr = (self.bind_addr, self.port)
            self.server = ThreadedHTTPServer(addr, KaffeineWebRequestHandler, owner=self)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            print(f"Kaffeine DVR Web Companion listening on http://{self.bind_addr}:{self.port}/", flush=True)
            return True
        except Exception as e:
            print(f"Failed to start Kaffeine DVR Web Server on port {self.port}: {e}", flush=True)
            self.server = None
            self.thread = None
            return False

    def stop(self):
        """Shuts down the background web server."""
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
        print("Kaffeine DVR Web Companion stopped.", flush=True)
