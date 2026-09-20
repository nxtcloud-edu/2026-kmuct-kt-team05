"""
한국어 요청 -> 구조화 의도 (규칙 기반).

LLM 없이 동작한다. 장소는 반드시 장소 DB 조회로 검증하고, 파서가 노드 ID 를
만들어내지 않는다. 확정 불가하면 needs_clarification 을 돌려준다.
"""

from __future__ import annotations

import re

# 제약 표현
NO_STAIRS = [
    "계단 없이", "계단없이", "계단 말고", "계단 빼고", "계단은 빼", "계단 피해",
    "계단 안", "계단 없는", "엘리베이터로", "승강기로",
]
STAIRS_OK = ["계단 있어도", "계단 괜찮", "계단 상관없", "계단 타도"]
WHEELCHAIR = ["휠체어", "휠체어로", "휠체어를 타", "배리어프리", "무장애"]
FASTEST = ["빠르게", "가장 빠", "최단", "빨리", "제일 빠"]
INDOOR = ["실내", "안으로", "건물 안", "비 안 맞", "실내로"]
COMFORT = ["편하게", "편한", "천천히", "무리 없"]
ELDERLY = ["노약자", "어르신", "다리가 불편", "무릎"]

ROOM_RE = re.compile(r"(?<!\d)(\d{3}(?:-\d)?)\s*(?:호|호실)?")
# '삼백삼십팔호' 같은 한글 수 표현은 범위에서 제외 (되묻기로 처리)


def parse(text: str, session: dict | None = None) -> dict:
    """텍스트 -> 정규화 의도. place_id 는 검증 후 상위에서 채운다."""
    t = (text or "").strip()
    low = t.replace(" ", "")
    prev = dict(session or {})

    # 기존 세션 제약을 이어받는다. '좀 더 빨리' 가 계단 금지를 지우지 않는다.
    no_stairs = bool(prev.get("no_stairs", False))
    wheelchair = bool(prev.get("wheelchair", False))
    prefer_indoor = bool(prev.get("prefer_indoor", False))
    objective = prev.get("objective") or "fastest"
    profile = prev.get("profile") or "normal"

    def has(words):
        return any(w.replace(" ", "") in low for w in words)

    # 부정/허용을 구별 (허용이 우선 해제)
    if has(STAIRS_OK):
        no_stairs = False
    elif has(NO_STAIRS):
        no_stairs = True

    if has(WHEELCHAIR):
        wheelchair = True
        no_stairs = True            # 휠체어는 계단 금지를 포함한다
        profile = "wheelchair"

    if has(ELDERLY):
        profile = "elderly"

    if has(FASTEST):
        objective = "fastest"
    if has(COMFORT):
        objective = "comfort"
    if has(INDOOR):
        prefer_indoor = True
        objective = "indoor"

    rooms = ROOM_RE.findall(t)
    dest_raw = None
    origin_raw = None
    if rooms:
        # '202에서 338로' 처럼 둘이면 앞을 출발, 뒤를 도착으로 본다
        if len(rooms) >= 2:
            origin_raw, dest_raw = rooms[0], rooms[1]
        else:
            dest_raw = rooms[0]
            # '~에서' 가 방 번호 뒤에 붙으면 출발지로 해석
            if re.search(rf"{re.escape(rooms[0])}\s*(?:호)?\s*에서", t):
                origin_raw, dest_raw = rooms[0], None

    needs = []
    if not dest_raw:
        needs.append("destination")
    if not origin_raw:
        needs.append("origin")

    return {
        "raw_text": t,
        "origin": {"raw_text": origin_raw, "place_id": None},
        "destination": {"raw_text": dest_raw, "place_id": None},
        "objective": objective,
        "profile": profile,
        "constraints": {"no_stairs": no_stairs, "wheelchair": wheelchair},
        "preferences": {"prefer_indoor": prefer_indoor},
        "needs_clarification": needs,
    }


def session_from(intent: dict) -> dict:
    """다음 발화에 이어받을 세션 상태."""
    return {
        "no_stairs": intent["constraints"]["no_stairs"],
        "wheelchair": intent["constraints"]["wheelchair"],
        "prefer_indoor": intent["preferences"]["prefer_indoor"],
        "objective": intent["objective"],
        "profile": intent["profile"],
    }
