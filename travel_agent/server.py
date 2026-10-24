import argparse
import json
import os
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from openai import APIError
from pydantic import Field, ValidationError

from .agent import AgentRequest, advise
from .domain import Activity, Flight, Hotel, Model
from .store import ConflictError, Store


class FlightUpdate(Model):
    version: int = Field(ge=0)
    data: Flight


class HotelUpdate(Model):
    version: int = Field(ge=0)
    data: Hotel


class ActivitiesUpdate(Model):
    version: int = Field(ge=0)
    data: list[Activity] = Field(max_length=500)


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, store, **kwargs):
        self.store = store
        super().__init__(*args, **kwargs)

    def reply(self, status, payload, content_type="application/json; charset=utf-8"):
        body = (json.dumps(payload, ensure_ascii=False).encode()
                if content_type.startswith("application/json") else payload)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; "
                         "style-src 'self'; script-src 'self'; frame-ancestors 'none'; "
                         "base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        static = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8")}
        if path in static:
            name, mime = static[path]
            return self.reply(200, (Path(__file__).parent / "static" / name).read_bytes(), mime)
        if path == "/api/health":
            return self.reply(200, {"ok": True,
                                    "ai_configured": bool(os.environ.get("TRAVEL_AGENT_API_KEY"))})
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "trips"]:
            try:
                trip = self.store.get(parts[2])
                return self.reply(200, {**trip.model_dump(mode="json"), "stage": trip.stage})
            except KeyError:
                return self.reply(404, {"error": "여행을 찾을 수 없습니다."})
        self.reply(404, {"error": "요청한 경로가 없습니다."})

    def do_POST(self):
        origin = self.headers.get("Origin")
        if ((origin and urlsplit(origin).netloc != self.headers.get("Host"))
                or self.headers.get("Sec-Fetch-Site") == "cross-site"):
            return self.reply(403, {"error": "다른 사이트에서 보낸 요청은 허용하지 않습니다."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 131072:
                return self.reply(413, {"error": "요청이 너무 큽니다."})
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                return self.reply(400, {"error": "객체 형식의 요청이 필요합니다."})
            path = urlsplit(self.path).path
            if path == "/api/trips":
                trip = self.store.create()
                return self.reply(201, {**trip.model_dump(mode="json"), "stage": trip.stage})
            parts = path.strip("/").split("/")
            if len(parts) != 4 or parts[:2] != ["api", "trips"]:
                return self.reply(404, {"error": "요청한 경로가 없습니다."})
            trip = self.store.get(parts[2])
            action = parts[3]
            models = {"flight": FlightUpdate, "hotel": HotelUpdate,
                      "activities": ActivitiesUpdate, "advice": AgentRequest}
            if action not in models:
                return self.reply(404, {"error": "알 수 없는 작업입니다."})
            request = models[action].model_validate(payload)
            if request.version != trip.version:
                raise ConflictError("일정이 변경되었습니다. 새로고침 후 다시 요청하세요.")
            if action == "advice":
                result = advise(trip, request)
                if self.store.get(trip.id).version != trip.version:
                    raise ConflictError("검색 중 일정이 바뀌었습니다. 최신 일정으로 다시 검색하세요.")
                return self.reply(200, result)
            if action == "flight":
                trip.set_flight(request.data)
            elif action == "hotel":
                trip.set_hotel(request.data)
            else:
                trip.set_activities(request.data)
            trip = self.store.save(trip, request.version)
            self.reply(200, {**trip.model_dump(mode="json"), "stage": trip.stage})
        except ValidationError as exc:
            messages = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                        for e in exc.errors(include_input=False, include_context=False)]
            self.reply(400, {"error": "\n".join(messages)})
        except (json.JSONDecodeError, UnicodeError):
            self.reply(400, {"error": "JSON 요청을 확인하세요."})
        except ValueError as exc:
            message = str(exc)
            self.reply(400, {"error": message})
        except KeyError:
            self.reply(404, {"error": "여행을 찾을 수 없습니다."})
        except ConflictError as exc:
            self.reply(409, {"error": str(exc)})
        except RuntimeError as exc:
            self.reply(503, {"error": str(exc)})
        except APIError:
            self.reply(502, {"error": "AI 요청에 실패했습니다. 키·모델 권한·네트워크 설정을 확인하세요."})
        except Exception:  # noqa: BLE001 -- keep the HTTP boundary from exposing internals
            self.reply(500, {"error": "처리 중 오류가 발생했습니다. 잠시 후 다시 시도하세요."})


def make_server(host="127.0.0.1", port=8000, db_path=None):
    path = db_path or os.environ.get("TRAVEL_AGENT_DB", ".data/trips.sqlite3")
    return ThreadingHTTPServer((host, port), partial(Handler, store=Store(path)))


def main():
    parser = argparse.ArgumentParser(description="여행 계획 에이전트")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = make_server(port=args.port)
    print(f"여행 에이전트 시작 · 포트 {server.server_port} · 종료: Ctrl+C", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
