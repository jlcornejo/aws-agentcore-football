"""Post-LLM tactical overrides — prompts suggest, code enforces.

Applied after parsing the LLM response. Corrects critical mistakes that
the LLM makes despite prompt instructions (happens ~40% of the time).
"""

import math
from state import (get_goal_positions, dist, _player_idx, _is_my_team, _possession_idx)
from tactics import lane_clear, shot_power, best_pass_target


def _cmd(cmd_type: str, pid: int, tid: int, params: dict, duration: int = 0) -> dict:
    return {"commandType": cmd_type, "playerId": pid, "teamId": tid,
            "parameters": params, "duration": duration}


def apply_overrides(commands: list, game_state: dict, team_id: int,
                    my_player_id: int, position_label: str) -> tuple:
    """Apply deterministic overrides to the LLM's command.
    
    Returns (commands, override_tag) where tag is None if nothing changed.
    """
    if not commands:
        return commands, None

    ball = game_state.get("ball", {}) or {}
    ball_pos = ball.get("position", {}) or {}
    players = game_state.get("players", []) or []
    
    me = next((p for p in players if _player_idx(p) == my_player_id and _is_my_team(p, team_id)), None)
    if me is None:
        return commands, None
    me_pos = me.get("position", {}) or {}
    
    my_goal_x, opp_goal_x = get_goal_positions(team_id)
    d_goal = dist(me_pos, {"x": opp_goal_x, "y": 0})
    opponents = [p for p in players if not _is_my_team(p, team_id)]
    
    poss_idx = _possession_idx(ball)
    i_have_ball = poss_idx == my_player_id
    
    cmd = commands[0]
    ctype = cmd.get("commandType", "")
    params = cmd.get("parameters", {}) or {}
    
    # === OVERRIDE 1: PHANTOM — SHOOT/PASS without ball wastes the tick ===
    if ctype in ("SHOOT", "PASS", "GK_DISTRIBUTE") and not i_have_ball:
        # Can't shoot/pass without the ball — do something useful instead
        d_ball = dist(me_pos, ball_pos)
        if d_ball < 12:
            return [_cmd("PRESS_BALL", my_player_id, team_id, {"intensity": 0.7}, duration=3)], "phantom-press"
        else:
            return [_cmd("INTERCEPT", my_player_id, team_id, {"aggressive": True}, duration=3)], "phantom-intercept"
    
    # === OVERRIDE 2: SHOT ENFORCEMENT — In range + clear lane = MUST shoot ===
    if i_have_ball and position_label in ("MID", "FWD1", "FWD2"):
        if d_goal < 25 and lane_clear(me_pos, opp_goal_x, opponents):
            if ctype != "SHOOT":
                pwr = shot_power(d_goal)
                return [_cmd("SHOOT", my_player_id, team_id, 
                           {"aim_location": "CENTER", "power": pwr})], "enforce-shot"
    
    # === OVERRIDE 3: GK DISTRIBUTE — GK with ball must distribute, never hold ===
    if i_have_ball and my_player_id == 0:
        if ctype not in ("GK_DISTRIBUTE", "SHOOT", "PASS"):
            # Find most advanced outfield teammate
            teammates = [p for p in players if _is_my_team(p, team_id) and _player_idx(p) != 0]
            if teammates:
                best = max(teammates, key=lambda p: p.get("position", {}).get("x", 0) * (1 if opp_goal_x > 0 else -1))
                target_id = _player_idx(best)
                d = dist(me_pos, best.get("position", {}))
                method = "KICK" if d > 25 else "THROW"
                return [_cmd("GK_DISTRIBUTE", my_player_id, team_id,
                           {"target_player_id": target_id, "method": method})], "gk-must-distribute"
    
    # === OVERRIDE 4: DEF with ball must pass forward immediately ===
    if i_have_ball and position_label == "DEF":
        if ctype == "MOVE_TO":  # DEF shouldn't dribble, should pass
            tid, pct, ptype = best_pass_target(me_pos, my_player_id, players, team_id, opp_goal_x, opponents)
            if tid is not None:
                return [_cmd("PASS", my_player_id, team_id,
                           {"target_player_id": tid, "type": ptype or "GROUND"})], "def-must-pass"
    
    # === OVERRIDE 5: NO CHASE — Only nearest player should press ===
    if ctype == "PRESS_BALL" and not i_have_ball:
        # Am I the nearest to the ball?
        my_d = dist(me_pos, ball_pos)
        teammates = [p for p in players if _is_my_team(p, team_id) and _player_idx(p) != my_player_id and _player_idx(p) != 0]
        for tm in teammates:
            if dist(tm.get("position", {}), ball_pos) < my_d:
                # Someone else is closer — I should hold position instead
                ax = me_pos.get("x", 0)  # hold current x
                ay = ball_pos.get("y", 0) * 0.3  # track ball laterally
                return [_cmd("MOVE_TO", my_player_id, team_id,
                           {"target_x": round(ax, 1), "target_y": round(ay, 1), "sprint": False})], "no-chase"
                break
    
    # === OVERRIDE 6: COUNTER — Deep possession + high press = through ball ===
    if i_have_ball and position_label in ("DEF", "MID"):
        opps_in_our_half = sum(1 for o in opponents if (o.get("position", {}).get("x", 0) * (-1 if opp_goal_x > 0 else 1)) > 0)
        if opps_in_our_half >= 3:
            # High press! Find most advanced forward
            forwards = [p for p in players if _is_my_team(p, team_id) and _player_idx(p) in (3, 4)]
            if forwards:
                best_fwd = max(forwards, key=lambda p: p.get("position", {}).get("x", 0) * (1 if opp_goal_x > 0 else -1))
                return [_cmd("PASS", my_player_id, team_id,
                           {"target_player_id": _player_idx(best_fwd), "type": "THROUGH"})], "counter"

    # === OVERRIDE 7: ROUTE-ONE — GK/DEF pressed with no ground outlet = AERIAL to FWD ===
    if i_have_ball and position_label in ("GK", "DEF"):
        nearest_opp = min((dist(me_pos, o.get("position", {})) for o in opponents), default=99)
        if nearest_opp < 10:  # under pressure
            # Check if any ground pass is safe
            has_safe_ground = False
            teammates = [p for p in players if _is_my_team(p, team_id) and _player_idx(p) != my_player_id]
            for tm in teammates:
                tm_pos = tm.get("position", {})
                if _pass_lane_clear(me_pos, tm_pos, opponents):
                    has_safe_ground = True
                    break
            if not has_safe_ground:
                # Loft AERIAL to the most advanced forward
                forwards = [p for p in players if _is_my_team(p, team_id) and _player_idx(p) in (3, 4)]
                if forwards:
                    best_fwd = max(forwards, key=lambda p: p.get("position", {}).get("x", 0) * (1 if opp_goal_x > 0 else -1))
                    return [_cmd("PASS", my_player_id, team_id,
                               {"target_player_id": _player_idx(best_fwd), "type": "AERIAL"})], "route-one"

    # === OVERRIDE 8: ATTACK SUPPORT — When teammate has ball, FWDs must move forward ===
    if not i_have_ball and position_label in ("FWD1", "FWD2"):
        # Check if a teammate has the ball
        teammate_has = False
        if poss_idx is not None:
            holder_p = next((p for p in players if _player_idx(p) == poss_idx), None)
            if holder_p and _is_my_team(holder_p, team_id):
                teammate_has = True
        if teammate_has:
            # FWDs should NOT be marking, holding stance, or moving backward
            if ctype in ("MARK", "SET_STANCE", "FOLLOW_PLAYER"):
                wing_y = -10.0 if position_label == "FWD1" else 10.0
                attack_x = opp_goal_x * 0.55  # push toward opponent goal
                return [_cmd("MOVE_TO", my_player_id, team_id,
                           {"target_x": round(attack_x, 1), "target_y": wing_y, "sprint": True})], "attack-support"
            # If MOVE_TO is going backward, redirect forward
            if ctype == "MOVE_TO":
                target_x = params.get("target_x", 0)
                direction = 1 if opp_goal_x > 0 else -1
                if target_x * direction < me_pos.get("x", 0) * direction:
                    # Moving backward while teammate has ball — push forward instead
                    wing_y = -10.0 if position_label == "FWD1" else 10.0
                    attack_x = opp_goal_x * 0.55
                    return [_cmd("MOVE_TO", my_player_id, team_id,
                               {"target_x": round(attack_x, 1), "target_y": wing_y, "sprint": True})], "attack-support"

    # === OVERRIDE 9: CARRY — MID/FWD with ball, not in range, no good pass = advance ===
    if i_have_ball and position_label in ("MID", "FWD1", "FWD2"):
        if d_goal > 25 and ctype in ("MOVE_TO", "SET_STANCE", "MARK"):
            # Check if we're already going forward
            if ctype == "MOVE_TO":
                target_x = params.get("target_x", 0)
                direction = 1 if opp_goal_x > 0 else -1
                # Only override if not advancing
                if target_x * direction <= me_pos.get("x", 0) * direction:
                    advance_x = me_pos.get("x", 0) + 12 * direction
                    advance_x = max(-50, min(50, advance_x))
                    return [_cmd("MOVE_TO", my_player_id, team_id,
                               {"target_x": round(advance_x, 1), "target_y": me_pos.get("y", 0) * 0.7, "sprint": True})], "carry"
            else:
                direction = 1 if opp_goal_x > 0 else -1
                advance_x = me_pos.get("x", 0) + 12 * direction
                advance_x = max(-50, min(50, advance_x))
                return [_cmd("MOVE_TO", my_player_id, team_id,
                           {"target_x": round(advance_x, 1), "target_y": me_pos.get("y", 0) * 0.7, "sprint": True})], "carry"

    # === OVERRIDE 10: TACKLE — Designated presser very close to carrier = SLIDE_TACKLE ===
    if not i_have_ball and ctype == "PRESS_BALL":
        # If I'm pressing and within tackle range, slide tackle
        if poss_idx is not None:
            holder_p = next((p for p in players if _player_idx(p) == poss_idx), None)
            if holder_p and not _is_my_team(holder_p, team_id):
                holder_pos = holder_p.get("position", {})
                d_carrier = dist(me_pos, holder_pos)
                if d_carrier < 4:
                    return [_cmd("SLIDE_TACKLE", my_player_id, team_id,
                               {"target_player_id": _player_idx(holder_p), "sprint": True, "distance": d_carrier})], "tackle"

    # === OVERRIDE 11: GK SMOTHER — GK intercepts loose ball in the box ===
    if my_player_id == 0 and not i_have_ball:
        ball_free = ball.get("isFree", False) or poss_idx is None
        d_ball = dist(me_pos, ball_pos)
        ball_in_box = abs(ball_pos.get("x", 0) - my_goal_x) < 18
        if ball_free and ball_in_box and d_ball < 12:
            return [_cmd("INTERCEPT", my_player_id, team_id,
                       {"aggressive": True}, duration=2)], "gk-smother"

    return commands, None


def _pass_lane_clear(me_pos: dict, target_pos: dict, opponents: list, radius: float = 5.0) -> bool:
    """Check if a pass from me to target is clear of opponents."""
    dx = target_pos.get("x", 0) - me_pos.get("x", 0)
    dy = target_pos.get("y", 0) - me_pos.get("y", 0)
    length_sq = dx * dx + dy * dy
    if length_sq < 1:
        return True
    length = math.sqrt(length_sq)
    for o in opponents:
        p = o.get("position", {}) or {}
        rx = p.get("x", 0) - me_pos.get("x", 0)
        ry = p.get("y", 0) - me_pos.get("y", 0)
        t = (rx * dx + ry * dy) / length_sq
        if t < 0.1 or t > 0.9:
            continue
        perp = abs((ry * dx - rx * dy) / length)
        if perp < radius:
            return False
    return True
