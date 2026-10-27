#!/usr/bin/env python3
"""统计经验区 Case/Skill 数"""
from common import *
for t in ("agent_case", "agent_skill"):
    s, d = post("/api/v2/memory/get", {"memory_type": t, "agent_id": AGENT, "page_size": 1})
    print(t, d["data"]["total_count"] if s == 200 else d)
