"""Universal DB query script for HermesMemoryControl.
Usage: python3 db_query.py <db_path> <query_type> [args_json]
"""
import sqlite3, json, sys, time

db_path = sys.argv[1]
query_type = sys.argv[2]
if len(sys.argv) > 3:
    arg3 = sys.argv[3]
    import os
    if os.path.isfile(arg3):
        with open(arg3, 'r') as _f: args = json.loads(_f.read())
    else:
        args = json.loads(arg3) if arg3 else {}
else:
    args = {}

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

def ts(epoch):
    if not epoch: return ""
    try: return time.strftime("%Y-%m-%d %H:%M", time.localtime(epoch))
    except: return ""

def row_to_dict(row):
    return dict(row) if row else {}

def rows_to_list(rows):
    return [dict(r) for r in rows]

result = {}

if query_type == "stats":
    r = {}
    r["active_facts"] = conn.execute("SELECT COUNT(*) FROM facts WHERE active=1").fetchone()[0]
    r["inactive_facts"] = conn.execute("SELECT COUNT(*) FROM facts WHERE active=0").fetchone()[0]
    r["topics"] = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
    r["sessions"] = conn.execute("SELECT COUNT(*) FROM memory_sessions").fetchone()[0]
    r["preferences"] = conn.execute("SELECT COUNT(*) FROM memory_preferences WHERE active=1").fetchone()[0]
    r["policies"] = conn.execute("SELECT COUNT(*) FROM memory_policies WHERE active=1").fetchone()[0]
    r["summaries"] = conn.execute("SELECT COUNT(*) FROM memory_summaries WHERE active=1").fetchone()[0]
    r["journals"] = conn.execute("SELECT COUNT(*) FROM memory_journals WHERE active=1").fetchone()[0]
    r["history_rows"] = conn.execute("SELECT COUNT(*) FROM memory_history").fetchone()[0]
    r["contradictions"] = conn.execute("SELECT COUNT(*) FROM contradictions").fetchone()[0]
    try:
        last = conn.execute("SELECT finished_at, stats_json FROM consolidation_runs ORDER BY id DESC LIMIT 1").fetchone()
        if last:
            r["last_consolidation"] = ts(last[0]) if last[0] else "never"
        else:
            r["last_consolidation"] = "never"
    except:
        r["last_consolidation"] = "unknown"
    result = r

elif query_type == "facts":
    category = args.get("category", "")
    search = args.get("search", "")
    include_inactive = args.get("include_inactive", False)
    limit = args.get("limit", 200)
    offset = args.get("offset", 0)

    where = []
    params = []
    if not include_inactive:
        where.append("active = 1")
    if category:
        where.append("category = ?")
        params.append(category)
    if search:
        where.append("(content LIKE ? OR subject_key LIKE ?)")
        params.extend(["%" + search + "%", "%" + search + "%"])

    where_str = "WHERE " + " AND ".join(where) if where else ""
    sql = f"SELECT id, content, category, topic, subject_key, value_key, importance, confidence, salience, active, exclusive, polarity, source, source_session_id, created_at, updated_at FROM facts {where_str} ORDER BY importance DESC, salience DESC, updated_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    result = {"facts": [{**dict(r), "created_at_str": ts(r["created_at"]), "updated_at_str": ts(r["updated_at"])} for r in rows]}

elif query_type == "topics":
    rows = conn.execute("SELECT t.id, t.slug, t.title, t.category, t.summary, t.importance, t.salience, t.updated_at, COUNT(tm.fact_id) as fact_count FROM topics t LEFT JOIN topic_membership tm ON t.id = tm.topic_id GROUP BY t.id ORDER BY t.salience DESC, t.importance DESC LIMIT 200").fetchall()
    result = {"topics": [{**dict(r), "updated_at_str": ts(r["updated_at"])} for r in rows]}

elif query_type == "sessions":
    rows = conn.execute("SELECT session_id, label, summary, status, started_at, ended_at, last_activity_at, created_at FROM memory_sessions ORDER BY last_activity_at DESC LIMIT 100").fetchall()
    result = {"sessions": [{**dict(r), "started_at_str": ts(r["started_at"]), "ended_at_str": ts(r["ended_at"]), "last_activity_str": ts(r["last_activity_at"])} for r in rows]}

elif query_type == "preferences":
    rows = conn.execute("SELECT id, preference_key, label, value, content, importance, salience, active, source_session_id, created_at, updated_at FROM memory_preferences WHERE active=1 ORDER BY importance DESC, salience DESC LIMIT 100").fetchall()
    result = {"preferences": [{**dict(r), "updated_at_str": ts(r["updated_at"])} for r in rows]}

elif query_type == "policies":
    rows = conn.execute("SELECT id, policy_key, label, content, importance, salience, active, source_session_id, created_at, updated_at FROM memory_policies WHERE active=1 ORDER BY importance DESC, salience DESC LIMIT 100").fetchall()
    result = {"policies": [{**dict(r), "updated_at_str": ts(r["updated_at"])} for r in rows]}

elif query_type == "contradictions":
    rows = conn.execute("""
        SELECT c.id, c.subject_key, c.resolution, c.created_at,
               w.content as winner_content, l.content as loser_content
        FROM contradictions c
        LEFT JOIN facts w ON c.winner_fact_id = w.id
        LEFT JOIN facts l ON c.loser_fact_id = l.id
        ORDER BY c.created_at DESC LIMIT 100
    """).fetchall()
    result = {"contradictions": [{**dict(r), "created_at_str": ts(r["created_at"])} for r in rows]}

## ── MUTATION HANDLERS ──

elif query_type == "update_fact":
    allowed = ["content","category","subject_key","value_key","importance","confidence","polarity","exclusive"]
    sets, params = [], []
    for k in allowed:
        if k in args and k != "id":
            sets.append(f"{k} = ?")
            params.append(args[k])
    if not sets:
        result = {"error": "no fields to update"}
    else:
        sets.append("updated_at = ?")
        params.append(time.time())
        params.append(args["id"])
        conn.execute("UPDATE facts SET " + ", ".join(sets) + " WHERE id = ?", params)
        conn.commit()
        result = {"success": True}

elif query_type == "toggle_fact_active":
    conn.execute("UPDATE facts SET active = CASE WHEN active=1 THEN 0 ELSE 1 END, updated_at = ? WHERE id = ?", [time.time(), args["id"]])
    conn.commit()
    result = {"success": True}

elif query_type == "delete_fact":
    conn.execute("DELETE FROM topic_membership WHERE fact_id = ?", [args["id"]])
    conn.execute("DELETE FROM facts WHERE id = ?", [args["id"]])
    conn.commit()
    result = {"success": True}

elif query_type == "update_topic":
    allowed = ["title","summary","importance","category"]
    sets, params = [], []
    for k in allowed:
        if k in args and k != "id":
            sets.append(f"{k} = ?")
            params.append(args[k])
    if not sets:
        result = {"error": "no fields to update"}
    else:
        sets.append("updated_at = ?")
        params.append(time.time())
        params.append(args["id"])
        conn.execute("UPDATE topics SET " + ", ".join(sets) + " WHERE id = ?", params)
        conn.commit()
        result = {"success": True}

elif query_type == "update_preference":
    allowed = ["label","value","content","importance"]
    sets, params = [], []
    for k in allowed:
        if k in args and k != "id":
            sets.append(f"{k} = ?")
            params.append(args[k])
    if not sets:
        result = {"error": "no fields to update"}
    else:
        sets.append("updated_at = ?")
        params.append(time.time())
        params.append(args["id"])
        conn.execute("UPDATE memory_preferences SET " + ", ".join(sets) + " WHERE id = ?", params)
        conn.commit()
        result = {"success": True}

elif query_type == "delete_preference":
    conn.execute("DELETE FROM memory_preferences WHERE id = ?", [args["id"]])
    conn.commit()
    result = {"success": True}

elif query_type == "update_policy":
    allowed = ["label","content","importance"]
    sets, params = [], []
    for k in allowed:
        if k in args and k != "id":
            sets.append(f"{k} = ?")
            params.append(args[k])
    if not sets:
        result = {"error": "no fields to update"}
    else:
        sets.append("updated_at = ?")
        params.append(time.time())
        params.append(args["id"])
        conn.execute("UPDATE memory_policies SET " + ", ".join(sets) + " WHERE id = ?", params)
        conn.commit()
        result = {"success": True}

elif query_type == "delete_policy":
    conn.execute("DELETE FROM memory_policies WHERE id = ?", [args["id"]])
    conn.commit()
    result = {"success": True}

elif query_type == "graph":
    # Build nodes and edges for 3D visualization
    nodes = []
    edges = []

    # Topic nodes
    topics = conn.execute("SELECT id, slug, title, category, importance, salience FROM topics ORDER BY salience DESC LIMIT 80").fetchall()
    for t in topics:
        nodes.append({
            "id": "t_" + str(t["id"]),
            "label": t["title"] or t["slug"],
            "type": "topic",
            "category": t["category"] or "general",
            "importance": t["importance"] or 5,
            "salience": t["salience"] or 0.5,
        })

    # Fact nodes (top facts only)
    facts = conn.execute("SELECT id, content, category, topic, subject_key, importance, salience FROM facts WHERE active=1 ORDER BY importance DESC, salience DESC LIMIT 150").fetchall()
    for f in facts:
        label = (f["content"] or "")[:60]
        nodes.append({
            "id": "f_" + str(f["id"]),
            "label": label,
            "type": "fact",
            "category": f["category"] or "general",
            "importance": f["importance"] or 5,
            "salience": f["salience"] or 0.5,
            "subject_key": f["subject_key"] or "",
        })

    # Topic-fact edges via topic_membership
    memberships = conn.execute("SELECT topic_id, fact_id FROM topic_membership").fetchall()
    topic_ids = {t["id"] for t in topics}
    fact_ids = {f["id"] for f in facts}
    for m in memberships:
        if m["topic_id"] in topic_ids and m["fact_id"] in fact_ids:
            edges.append({"source": "t_" + str(m["topic_id"]), "target": "f_" + str(m["fact_id"]), "type": "supports"})

    # Contradiction edges
    contras = conn.execute("SELECT winner_fact_id, loser_fact_id FROM contradictions").fetchall()
    for c in contras:
        if c["winner_fact_id"] in fact_ids and c["loser_fact_id"] in fact_ids:
            edges.append({"source": "f_" + str(c["winner_fact_id"]), "target": "f_" + str(c["loser_fact_id"]), "type": "contradicts"})

    # Session-fact edges via links table
    try:
        links = conn.execute("SELECT source_kind, source_id, target_kind, target_id, link_type FROM memory_links WHERE link_type IN ('derived_from_episode','supports','contradicts') LIMIT 500").fetchall()
        for lk in links:
            sid = lk["source_kind"][0] + "_" + str(lk["source_id"])
            tid = lk["target_kind"][0] + "_" + str(lk["target_id"])
            node_ids = {n["id"] for n in nodes}
            if sid in node_ids and tid in node_ids:
                edges.append({"source": sid, "target": tid, "type": lk["link_type"]})
    except:
        pass

    # Preference nodes
    prefs = conn.execute("SELECT id, preference_key, label, importance, salience FROM memory_preferences WHERE active=1 ORDER BY importance DESC LIMIT 30").fetchall()
    for p in prefs:
        nodes.append({
            "id": "p_" + str(p["id"]),
            "label": p["label"] or p["preference_key"] or "",
            "type": "preference",
            "category": "user_pref",
            "importance": p["importance"] or 8,
            "salience": p["salience"] or 0.9,
        })

    result = {"nodes": nodes, "edges": edges}

elif query_type == "wiki_list":
    import os
    wiki_dir = args.get("wiki_dir", "")
    if not wiki_dir or not os.path.isdir(wiki_dir):
        result = {"files": [], "error": "wiki dir not found: " + wiki_dir}
    else:
        files = []
        for root, dirs, fnames in os.walk(wiki_dir):
            for fn in sorted(fnames):
                if fn.endswith(".md"):
                    rel = os.path.relpath(os.path.join(root, fn), wiki_dir).replace("\\", "/")
                    files.append(rel)
        result = {"files": sorted(files)}

elif query_type == "wiki_read":
    import os
    fpath = args.get("path", "")
    if not fpath or not os.path.isfile(fpath):
        result = {"content": "", "error": "file not found: " + fpath}
    else:
        with open(fpath, "r", encoding="utf-8") as f:
            result = {"content": f.read()}

else:
    result = {"error": "unknown query_type: " + query_type}

conn.close()
print(json.dumps(result, default=str))
