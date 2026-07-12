"""Viewer gráfico estilo retro — visualiza tu equipo en una cancha 2D con Pygame.

Inspirado en International Superstar Soccer / Sensible Soccer.

Usage:
    python viewer.py                # Fallback mode (sin AWS)
    python viewer.py --llm          # Con LLM real (requiere AWS)
    python viewer.py --ticks 50     # Duración del partido
    python viewer.py --speed 2      # Velocidad de simulación (1=normal, 3=rápido)
"""

import sys
import os
import math
import time
import random

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
from test_helpers import mock_agentcore, TEAM_ID
mock_agentcore()
from state import summarize_state
from parsing import parse_commands
from fallback import (
    build_fallback, GK_CONFIG, DEF_CONFIG, MID_CONFIG, FWD1_CONFIG, FWD2_CONFIG,
)

# ═══════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════
SCREEN_W, SCREEN_H = 1280, 680
LOG_PANEL_W = 310
FIELD_MARGIN = 40
FIELD_X = FIELD_MARGIN
FIELD_Y = FIELD_MARGIN + 30
FIELD_W = SCREEN_W - FIELD_MARGIN * 2 - LOG_PANEL_W
FIELD_H = SCREEN_H - FIELD_MARGIN * 2 - 60
PANEL_H = 50
LOG_X = SCREEN_W - LOG_PANEL_W + 5
LOG_Y = 5

# Colors
COL_BG = (20, 28, 20)
COL_FIELD = (34, 120, 50)
COL_FIELD_DARK = (28, 100, 42)
COL_LINE = (220, 220, 220)
COL_GOAL = (255, 255, 255)
COL_HOME = (0, 180, 255)       # Cyan/blue
COL_HOME_DARK = (0, 100, 180)
COL_AWAY = (255, 60, 60)       # Red
COL_AWAY_DARK = (180, 30, 30)
COL_BALL = (255, 220, 50)
COL_BALL_SHADOW = (40, 40, 40)
COL_TEXT = (240, 240, 240)
COL_TEXT_DIM = (150, 150, 150)
COL_SCORE_BG = (30, 30, 30)
COL_STAMINA_OK = (50, 200, 80)
COL_STAMINA_MED = (220, 180, 30)
COL_STAMINA_LOW = (220, 50, 50)

GOAL_HALF_PX = int(FIELD_H * 7 / 35)  # proportional to field


# ═══════════════════════════════════════════════════════════════
# GAME SIMULATION (same logic as simulate.py)
# ═══════════════════════════════════════════════════════════════
class Ball:
    def __init__(self):
        self.x, self.y = 0.0, 0.0
        self.vx, self.vy = 0.0, 0.0
        self.possessor = None

    def update(self):
        if self.possessor is None:
            self.x += self.vx
            self.y += self.vy
            self.vx *= 0.92  # Less friction — passes travel further
            self.vy *= 0.92
            if abs(self.vx) < 0.15: self.vx = 0
            if abs(self.vy) < 0.15: self.vy = 0
            self.x = max(-55, min(55, self.x))
            self.y = max(-35, min(35, self.y))


class Player:
    def __init__(self, team, idx, x, y, role):
        self.team, self.idx = team, idx
        self.x, self.y = x, y
        self.stamina = 0.95
        self.has_ball = False
        self.role = role
        self.last_cmd = ""
        self.last_params = {}

    def move_toward(self, tx, ty, speed=2.0):
        dx, dy = tx - self.x, ty - self.y
        d = math.sqrt(dx*dx + dy*dy)
        if d > 0.5:
            step = min(speed, d)
            self.x += (dx/d)*step
            self.y += (dy/d)*step
            self.stamina = max(0, self.stamina - (0.005 if speed > 3 else 0.002))
        self.x = max(-55, min(55, self.x))
        self.y = max(-35, min(35, self.y))


class Match:
    def __init__(self):
        self.score = [0, 0]
        self.tick = 0
        self.max_ticks = 30
        self.ball = Ball()
        self.goal_event = None
        self.goal_timer = 0
        self.home = [
            Player(0, 0, -52, 0, "GK"), Player(0, 1, -25, -10, "DEF"),
            Player(0, 2, -25, 10, "MID"), Player(0, 3, -5, -8, "FWD1"),
            Player(0, 4, -5, 8, "FWD2"),
        ]
        self.away = [
            Player(1, 0, 48, 0, "GK"), Player(1, 1, 25, 8, "DEF"),
            Player(1, 2, 5, -3, "MID"), Player(1, 3, -5, -10, "FWD"),
            Player(1, 4, -5, 10, "FWD"),
        ]
        self._give_ball(0, 3)  # FWD1 starts with ball at kickoff

    def _give_ball(self, team, pid):
        for p in self.home + self.away:
            p.has_ball = False
        owner = (self.home if team == 0 else self.away)[pid]
        owner.has_ball = True
        self.ball.possessor = (team, pid)
        self.ball.x, self.ball.y = owner.x, owner.y
        self.ball.vx = self.ball.vy = 0

    def build_state(self):
        players = []
        for p in self.home + self.away:
            players.append({
                "agentId": f"agentId_{p.idx}",
                "teamCode": "home" if p.team == 0 else "away",
                "position": {"x": p.x, "y": p.y},
                "velocity": {"x": 0, "y": 0},
                "stamina": p.stamina, "speed": 0, "isSprinting": False,
                "orientation": 0, "currentAction": 0, "lastAction": p.last_cmd,
            })
        poss = f"agentId_{self.ball.possessor[1]}" if self.ball.possessor else None
        return {
            "tick": self.tick, "gameTime": self.tick * 2.0,
            "playMode": "OPEN_PLAY", "modeTeamId": None,
            "score": {"home": self.score[0], "away": self.score[1]},
            "ball": {
                "position": {"x": self.ball.x, "y": self.ball.y, "z": 0},
                "velocity": {"x": self.ball.vx, "y": self.ball.vy, "z": 0},
                "isFree": self.ball.possessor is None,
                "possessionAgentId": poss,
                "rotation": {}, "angularVelocity": {},
            },
            "players": players, "teamChat": [],
        }

    def apply_cmd(self, player, cmd):
        ct = cmd.get("commandType", "SET_STANCE")
        params = cmd.get("parameters", {})
        player.last_cmd = ct
        player.last_params = params

        if ct == "SHOOT" and player.has_ball:
            power = params.get("power", 0.8)
            player.has_ball = False
            self.ball.possessor = None
            self.ball.x, self.ball.y = player.x, player.y

            # Aim toward the GOAL (x=55, y=target based on aim_location)
            goal_x = 55.0
            aim = params.get("aim_location", "CENTER")
            # aim_location selects a spot within the goal (y=-7 to y=+7)
            aim_y = {"TL": -5, "TR": -5, "BL": 5, "BR": 5, "CENTER": 0}.get(aim, 0)

            dx = goal_x - player.x
            dy = aim_y - player.y
            dist_to_goal = math.sqrt(dx*dx + dy*dy) or 1

            speed = power * 14
            self.ball.vx = (dx / dist_to_goal) * speed
            self.ball.vy = (dy / dist_to_goal) * speed
        elif ct in ("PASS", "GK_DISTRIBUTE") and player.has_ball:
            tid = params.get("target_player_id", 2)
            target = next((p for p in self.home if p.idx == tid), None)
            if target:
                player.has_ball = False
                self.ball.possessor = None
                self.ball.x, self.ball.y = player.x, player.y
                dx, dy = target.x - player.x, target.y - player.y
                d = math.sqrt(dx*dx + dy*dy) or 1
                # Speed based on type: AERIAL/THROUGH are faster for long range
                ptype = params.get("type", "GROUND")
                if ct == "GK_DISTRIBUTE":
                    spd = 12
                elif ptype in ("AERIAL", "THROUGH"):
                    spd = 11
                else:
                    spd = 8  # GROUND pass — faster than before
                self.ball.vx, self.ball.vy = (dx/d)*spd, (dy/d)*spd
        elif ct == "MOVE_TO":
            tx, ty = params.get("target_x", player.x), params.get("target_y", player.y)
            player.move_toward(tx, ty, 4.5 if params.get("sprint") else 2.5)
        elif ct in ("PRESS_BALL", "INTERCEPT"):
            player.move_toward(self.ball.x, self.ball.y, 3.5)
        elif ct in ("MARK", "FOLLOW_PLAYER"):
            tid = params.get("target_player_id", 0)
            target = next((p for p in self.away if p.idx == tid), None)
            if target:
                player.move_toward(target.x, target.y, 2.5)
        elif ct == "SLIDE_TACKLE":
            player.move_toward(self.ball.x, self.ball.y, 5.0)
            if self.ball.possessor and self.ball.possessor[0] == 1:
                carrier = self.away[self.ball.possessor[1]]
                d = math.sqrt((player.x-carrier.x)**2 + (player.y-carrier.y)**2)
                if d < 4 and random.random() < 0.5:
                    carrier.has_ball = False
                    self._give_ball(0, player.idx)

    def run_away_ai(self):
        for p in self.away:
            if p.has_ball:
                if p.x < -30:
                    p.has_ball = False
                    self.ball.possessor = None
                    self.ball.x, self.ball.y = p.x, p.y
                    self.ball.vx, self.ball.vy = -12, random.uniform(-4, 4)
                    p.last_cmd = "SHOOT"
                else:
                    p.move_toward(p.x - 5, p.y + random.uniform(-2, 2), 2.5)
                    self.ball.x, self.ball.y = p.x, p.y
                    p.last_cmd = "DRIBBLE"
            else:
                d_ball = math.sqrt((p.x-self.ball.x)**2 + (p.y-self.ball.y)**2)
                if d_ball < 12 and self.ball.possessor and self.ball.possessor[0] == 0:
                    p.move_toward(self.ball.x, self.ball.y, 3.0)
                    p.last_cmd = "PRESS"
                elif p.role == "GK":
                    p.move_toward(48, max(-7, min(7, self.ball.y*0.3)), 1.5)
                    p.last_cmd = "POS"
                else:
                    defaults = {1:(18,6), 2:(3,-3), 3:(-14,-10), 4:(-14,10)}
                    dx, dy = defaults.get(p.idx, (0,0))
                    p.move_toward(dx, dy, 1.5)
                    p.last_cmd = "POS"

    def check_possession(self):
        if self.ball.possessor is not None:
            return
        for p in self.home + self.away:
            d = math.sqrt((p.x-self.ball.x)**2 + (p.y-self.ball.y)**2)
            if d < 5:  # Larger pickup radius — players receive passes easier
                self._give_ball(p.team, p.idx)
                return

    def check_goals(self):
        self.goal_event = None
        if self.ball.x >= 54 and abs(self.ball.y) < 7:
            self.score[0] += 1
            self.goal_event = "HOME"
            self.goal_timer = 60
            self._reset_kickoff(1)
        elif self.ball.x <= -54 and abs(self.ball.y) < 7:
            self.score[1] += 1
            self.goal_event = "AWAY"
            self.goal_timer = 60
            self._reset_kickoff(0)
        if abs(self.ball.x) > 55:
            self.ball.x = max(-54, min(54, self.ball.x))
            self.ball.vx = 0
        if abs(self.ball.y) > 35:
            self.ball.y = max(-34, min(34, self.ball.y))
            self.ball.vy = 0

    def _reset_kickoff(self, team):
        for p in self.home:
            p.x, p.y = [(-52,0),(-25,-10),(-25,10),(-5,-8),(-5,8)][p.idx]
        for p in self.away:
            p.x, p.y = [(48,0),(25,8),(5,0),(-5,-10),(-5,10)][p.idx]
        self._give_ball(team, 3)


# ═══════════════════════════════════════════════════════════════
# RENDERER
# ═══════════════════════════════════════════════════════════════
def field_to_screen(x, y):
    """Convert field coords (-55..55, -35..35) to screen pixels."""
    sx = FIELD_X + (x + 55) / 110 * FIELD_W
    sy = FIELD_Y + (y + 35) / 70 * FIELD_H
    return int(sx), int(sy)


def draw_field(screen):
    """Draw the football pitch with stripes and markings."""
    # Grass stripes
    stripe_w = FIELD_W // 10
    for i in range(10):
        col = COL_FIELD if i % 2 == 0 else COL_FIELD_DARK
        pygame.draw.rect(screen, col, (FIELD_X + i*stripe_w, FIELD_Y, stripe_w, FIELD_H))

    # Border
    pygame.draw.rect(screen, COL_LINE, (FIELD_X, FIELD_Y, FIELD_W, FIELD_H), 2)

    # Center line
    cx = FIELD_X + FIELD_W // 2
    pygame.draw.line(screen, COL_LINE, (cx, FIELD_Y), (cx, FIELD_Y + FIELD_H), 1)

    # Center circle
    pygame.draw.circle(screen, COL_LINE, (cx, FIELD_Y + FIELD_H//2), 40, 1)
    pygame.draw.circle(screen, COL_LINE, (cx, FIELD_Y + FIELD_H//2), 4)

    # Goals
    goal_h = GOAL_HALF_PX * 2
    goal_w = 12
    cy = FIELD_Y + FIELD_H // 2
    # Left goal
    pygame.draw.rect(screen, COL_GOAL, (FIELD_X - goal_w, cy - goal_h//2, goal_w, goal_h), 2)
    # Right goal
    pygame.draw.rect(screen, COL_GOAL, (FIELD_X + FIELD_W, cy - goal_h//2, goal_w, goal_h), 2)

    # Penalty areas
    pa_w, pa_h = int(FIELD_W * 0.15), int(FIELD_H * 0.55)
    pygame.draw.rect(screen, COL_LINE, (FIELD_X, cy - pa_h//2, pa_w, pa_h), 1)
    pygame.draw.rect(screen, COL_LINE, (FIELD_X + FIELD_W - pa_w, cy - pa_h//2, pa_w, pa_h), 1)


def draw_player(screen, font, player, is_home):
    """Draw a player as a colored circle with number/letter."""
    sx, sy = field_to_screen(player.x, player.y)
    col = COL_HOME if is_home else COL_AWAY
    col_dark = COL_HOME_DARK if is_home else COL_AWAY_DARK

    # Shadow
    pygame.draw.circle(screen, (20, 20, 20), (sx + 2, sy + 3), 11)

    # Body
    pygame.draw.circle(screen, col, (sx, sy), 11)
    pygame.draw.circle(screen, col_dark, (sx, sy), 11, 2)

    # Number/letter
    label = str(player.idx) if is_home else chr(ord('A') + player.idx)
    text = font.render(label, True, (255, 255, 255))
    text_rect = text.get_rect(center=(sx, sy))
    screen.blit(text, text_rect)

    # Ball indicator
    if player.has_ball:
        pygame.draw.circle(screen, COL_BALL, (sx + 10, sy - 8), 5)
        pygame.draw.circle(screen, (180, 150, 0), (sx + 10, sy - 8), 5, 1)

    # Role label (small, below)
    role_text = font.render(player.role, True, COL_TEXT_DIM)
    screen.blit(role_text, (sx - role_text.get_width()//2, sy + 13))


def draw_ball(screen, ball):
    """Draw the ball with shadow."""
    if ball.possessor is not None:
        return
    sx, sy = field_to_screen(ball.x, ball.y)
    pygame.draw.circle(screen, COL_BALL_SHADOW, (sx + 2, sy + 3), 6)
    pygame.draw.circle(screen, COL_BALL, (sx, sy), 6)
    pygame.draw.circle(screen, (200, 170, 30), (sx, sy), 6, 1)


def draw_scoreboard(screen, font_big, font_small, match):
    """Draw TV-style scoreboard in top-left corner."""
    # Compact box in top-left
    box_w, box_h = 220, 36
    box_x, box_y = FIELD_X + 10, FIELD_Y + 10

    # Background with slight transparency
    surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
    surf.fill((20, 20, 20, 200))
    screen.blit(surf, (box_x, box_y))
    pygame.draw.rect(screen, (80, 80, 80), (box_x, box_y, box_w, box_h), 1)

    # HOME score AWAY
    home_label = font_small.render("HOME", True, COL_HOME)
    screen.blit(home_label, (box_x + 8, box_y + 4))

    score_text = font_big.render(f"{match.score[0]} - {match.score[1]}", True, COL_TEXT)
    score_rect = score_text.get_rect(center=(box_x + box_w//2, box_y + box_h//2))
    screen.blit(score_text, score_rect)

    away_label = font_small.render("AWAY", True, COL_AWAY)
    screen.blit(away_label, (box_x + box_w - away_label.get_width() - 8, box_y + 4))

    # Time below score
    time_left = max(0, (match.max_ticks - match.tick) * 2)
    minutes = int(time_left) // 60
    seconds = int(time_left) % 60
    time_text = font_small.render(f"{minutes}:{seconds:02d}  T{match.tick}", True, COL_TEXT_DIM)
    screen.blit(time_text, (box_x + 8, box_y + box_h - 14))


def draw_action_panel(screen, font, match):
    """Draw action log at the bottom."""
    y_start = SCREEN_H - PANEL_H
    pygame.draw.rect(screen, COL_SCORE_BG, (0, y_start, SCREEN_W - LOG_PANEL_W, PANEL_H))

    x = 10
    for p in match.home:
        cmd = p.last_cmd or "---"
        col = COL_HOME
        label = f"{p.idx}:{cmd[:8]}"
        text = font.render(label, True, col)
        screen.blit(text, (x, y_start + 5))

        # Stamina bar
        bar_w = 60
        bar_h = 6
        stam_col = COL_STAMINA_OK if p.stamina > 0.6 else (COL_STAMINA_MED if p.stamina > 0.3 else COL_STAMINA_LOW)
        pygame.draw.rect(screen, (50, 50, 50), (x, y_start + 25, bar_w, bar_h))
        pygame.draw.rect(screen, stam_col, (x, y_start + 25, int(bar_w * p.stamina), bar_h))

        # Ball indicator
        if p.has_ball:
            pygame.draw.circle(screen, COL_BALL, (x + bar_w + 8, y_start + 15), 4)

        x += 100

    # Ball possession
    x = SCREEN_W - LOG_PANEL_W - 280
    poss_text = ""
    if match.ball.possessor:
        team_name = "HOME" if match.ball.possessor[0] == 0 else "AWAY"
        poss_text = f"Ball: {team_name} P{match.ball.possessor[1]}"
    else:
        poss_text = f"Ball: free ({match.ball.x:.0f},{match.ball.y:.0f})"
    text = font.render(poss_text, True, COL_TEXT_DIM)
    screen.blit(text, (x, y_start + 15))


def draw_goal_celebration(screen, font_big, event):
    """Flash GOAL text."""
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 100))
    screen.blit(overlay, (0, 0))

    col = COL_HOME if event == "HOME" else COL_AWAY
    team = "¡¡¡GOOOL TU EQUIPO!!!" if event == "HOME" else "Gol del rival..."
    text = font_big.render(team, True, col)
    rect = text.get_rect(center=(SCREEN_W//2 - LOG_PANEL_W//2, SCREEN_H//2))
    screen.blit(text, rect)


class EventLog:
    """Rolling event log displayed on the right panel."""

    MAX_ENTRIES = 40
    ROLE_NAMES = {0: "GK", 1: "DEF", 2: "MID", 3: "FW1", 4: "FW2"}

    def __init__(self):
        self.entries = []  # list of (tick, color, text)

    def add(self, tick, color, text):
        self.entries.append((tick, color, text))
        if len(self.entries) > self.MAX_ENTRIES:
            self.entries.pop(0)

    def log_tick(self, match):
        """Log all commands executed this tick — helps understand available actions."""
        tick = match.tick

        # Goals (highest priority)
        if match.goal_event:
            if match.goal_event == "HOME":
                self.add(tick, COL_HOME, f"⚽ ¡¡GOOOL!! Tu equipo anota!")
            else:
                self.add(tick, COL_AWAY, f"⚽ Gol del rival")
            self.add(tick, COL_TEXT_DIM, f"   Score: {match.score[0]} - {match.score[1]}")
            return

        # Log ALL home player commands with params
        for p in match.home:
            cmd = p.last_cmd
            if not cmd:
                continue
            params = p.last_params or {}

            # Format params compactly
            if cmd == "SHOOT":
                detail = f"aim={params.get('aim_location','?')} pwr={params.get('power','?')}"
                self.add(tick, COL_HOME, f"💥 {self.ROLE_NAMES[p.idx]} SHOOT {detail}")
            elif cmd == "PASS":
                tid = params.get("target_player_id", "?")
                tgt = self.ROLE_NAMES.get(tid, f"P{tid}")
                ptype = params.get("type", "GROUND")
                self.add(tick, COL_HOME, f"→ {self.ROLE_NAMES[p.idx]} PASS→{tgt} ({ptype})")
            elif cmd == "GK_DISTRIBUTE":
                tid = params.get("target_player_id", "?")
                tgt = self.ROLE_NAMES.get(tid, f"P{tid}")
                method = params.get("method", "THROW")
                self.add(tick, COL_HOME, f"→ {self.ROLE_NAMES[p.idx]} GK_DISTRIBUTE→{tgt} ({method})")
            elif cmd == "MOVE_TO":
                tx = params.get("target_x", 0)
                ty = params.get("target_y", 0)
                sprint = "🏃" if params.get("sprint") else ""
                self.add(tick, COL_TEXT_DIM, f"  {self.ROLE_NAMES[p.idx]} MOVE_TO({tx:.0f},{ty:.0f}){sprint}")
            elif cmd == "PRESS_BALL":
                inten = params.get("intensity", 0.7)
                self.add(tick, (100, 180, 255), f"⚡ {self.ROLE_NAMES[p.idx]} PRESS_BALL int={inten}")
            elif cmd == "MARK":
                tid = params.get("target_player_id", "?")
                tight = params.get("tightness", "TIGHT")
                self.add(tick, (100, 180, 255), f"🛡 {self.ROLE_NAMES[p.idx]} MARK P{tid} {tight}")
            elif cmd == "INTERCEPT":
                aggr = "aggr" if params.get("aggressive") else ""
                self.add(tick, (100, 180, 255), f"🛡 {self.ROLE_NAMES[p.idx]} INTERCEPT {aggr}")
            elif cmd == "FOLLOW_PLAYER":
                tid = params.get("target_player_id", "?")
                self.add(tick, (100, 180, 255), f"👁 {self.ROLE_NAMES[p.idx]} FOLLOW P{tid}")
            elif cmd == "SLIDE_TACKLE":
                self.add(tick, (255, 200, 50), f"⚠️  {self.ROLE_NAMES[p.idx]} SLIDE_TACKLE!")
            elif cmd == "SET_STANCE":
                stances = {0: "Balanced", 1: "Attack", 2: "Defend"}
                stance = stances.get(params.get("stance", 0), "?")
                self.add(tick, COL_TEXT_DIM, f"  {self.ROLE_NAMES[p.idx]} SET_STANCE={stance}")
            else:
                self.add(tick, COL_TEXT_DIM, f"  {self.ROLE_NAMES[p.idx]} {cmd}")

        # Away key events (only shots to reduce noise)
        for p in match.away:
            if p.last_cmd == "SHOOT":
                self.add(tick, COL_AWAY, f"💥 Rival {chr(65+p.idx)} SHOOT!")

    def copy_to_clipboard(self):
        """Copy all log entries to clipboard as plain text."""
        lines = []
        for tick, color, text in self.entries:
            lines.append(f"[T{tick:3}] {text}")
        full_text = "\n".join(lines)

        # Use pbcopy on macOS
        try:
            import subprocess
            process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
            process.communicate(full_text.encode('utf-8'))
            return True
        except Exception:
            return False

    def draw(self, screen, font):
        """Draw the log panel on the right side."""
        # Panel background
        panel_rect = pygame.Rect(SCREEN_W - LOG_PANEL_W, 0, LOG_PANEL_W, SCREEN_H)
        pygame.draw.rect(screen, (25, 25, 30), panel_rect)
        pygame.draw.line(screen, (60, 60, 70), (SCREEN_W - LOG_PANEL_W, 0),
                         (SCREEN_W - LOG_PANEL_W, SCREEN_H), 2)

        # Header + Copy button
        header = font.render("📋 EVENT LOG", True, COL_TEXT)
        screen.blit(header, (LOG_X + 5, LOG_Y + 8))

        # Draw copy button
        btn_w, btn_h = 60, 18
        btn_x = SCREEN_W - btn_w - 10
        btn_y = LOG_Y + 5
        self._copy_btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        pygame.draw.rect(screen, (60, 60, 80), self._copy_btn_rect)
        pygame.draw.rect(screen, (100, 100, 120), self._copy_btn_rect, 1)
        btn_text = font.render("[C]opy", True, COL_TEXT_DIM)
        screen.blit(btn_text, (btn_x + 5, btn_y + 3))

        pygame.draw.line(screen, (60, 60, 70), (LOG_X, LOG_Y + 28),
                         (SCREEN_W - 5, LOG_Y + 28), 1)

        # Entries (most recent at bottom, scroll up)
        y = LOG_Y + 35
        line_h = 16
        max_visible = (SCREEN_H - 50) // line_h

        visible = self.entries[-max_visible:]
        for tick, color, text in visible:
            # Tick number
            tick_text = font.render(f"{tick:2}", True, (80, 80, 90))
            screen.blit(tick_text, (LOG_X, y))

            # Event text (truncate if needed)
            display_text = text[:34]
            evt_text = font.render(display_text, True, color)
            screen.blit(evt_text, (LOG_X + 22, y))
            y += line_h


# ═══════════════════════════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════════════════════════
def main():
    max_ticks = 30
    use_llm = "--llm" in sys.argv
    speed = 1

    for i, arg in enumerate(sys.argv):
        if arg == "--ticks" and i+1 < len(sys.argv):
            try: max_ticks = int(sys.argv[i+1])
            except: pass
        if arg == "--speed" and i+1 < len(sys.argv):
            try: speed = int(sys.argv[i+1])
            except: pass

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("⚽ Agentic Football Cup — Viewer")
    clock = pygame.time.Clock()

    font_small = pygame.font.SysFont("Menlo", 12)
    font_med = pygame.font.SysFont("Menlo", 14, bold=True)
    font_big = pygame.font.SysFont("Menlo", 22, bold=True)

    # Setup
    configs = {0: GK_CONFIG, 1: DEF_CONFIG, 2: MID_CONFIG, 3: FWD1_CONFIG, 4: FWD2_CONFIG}
    fallbacks = {pid: build_fallback(cfg) for pid, cfg in configs.items()}
    labels = {0: "GK", 1: "DEF", 2: "MID", 3: "FWD1", 4: "FWD2"}

    agents = {}
    agent_model_map = {}
    if use_llm:
        import importlib
        from strands import Agent
        from strands.models import BedrockModel

        # Same model distribution as official workshop teams
        agent_model_map = {
            0: ("us.amazon.nova-micro-v1:0", "Micro"),   # GK - fast
            1: ("us.amazon.nova-lite-v1:0", "Lite"),     # DEF - balanced
            2: ("us.amazon.nova-pro-v1:0", "Pro"),       # MID - smartest
            3: ("us.amazon.nova-micro-v1:0", "Micro"),   # FWD1 - fast
            4: ("us.amazon.nova-lite-v1:0", "Lite"),     # FWD2 - balanced
        }

        for pid, agent_dir in enumerate(["ai-gk", "ai-def", "ai-mid", "ai-fwd1", "ai-fwd2"]):
            model_id = agent_model_map[pid][0]
            model = BedrockModel(model_id=model_id)
            spec = importlib.util.spec_from_file_location(
                f"agent_{pid}",
                os.path.join(os.path.dirname(__file__), agent_dir, "src", "main.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            agents[pid] = Agent(model=model, system_prompt=mod.SYSTEM_PROMPT)

    match = Match()
    match.max_ticks = max_ticks
    event_log = EventLog()
    event_log.add(0, COL_TEXT, "🏟️  Partido iniciado")
    if use_llm:
        event_log.add(0, COL_HOME, "   Modo: LLM")
        event_log.add(0, COL_TEXT_DIM, "  Modelos:")
        for pid, (_, label) in agent_model_map.items():
            event_log.add(0, COL_TEXT_DIM, f"    {labels[pid]}: Nova {label}")
    else:
        event_log.add(0, COL_TEXT_DIM, "   Modo: Fallback (reglas)")

    tick_interval = 2000 // speed  # ms between ticks
    last_tick_time = pygame.time.get_ticks()
    running = True
    paused = False
    finished = False

    # === COUNTDOWN 3..2..1..GO! ===
    font_countdown = pygame.font.SysFont("Menlo", 72, bold=True)
    countdown_texts = ["3", "2", "1", "GO!"]
    for count_text in countdown_texts:
        # Render the field with players in position (so you can see formation)
        screen.fill(COL_BG)
        draw_field(screen)
        draw_ball(screen, match.ball)
        for p in match.away:
            draw_player(screen, font_small, p, False)
        for p in match.home:
            draw_player(screen, font_small, p, True)
        draw_scoreboard(screen, font_big, font_small, match)
        event_log.draw(screen, font_small)

        # Draw countdown overlay
        overlay = pygame.Surface((SCREEN_W - LOG_PANEL_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        screen.blit(overlay, (0, 0))

        col = COL_BALL if count_text == "GO!" else COL_TEXT
        txt = font_countdown.render(count_text, True, col)
        rect = txt.get_rect(center=((SCREEN_W - LOG_PANEL_W) // 2, SCREEN_H // 2))
        screen.blit(txt, rect)

        # Formation label
        formation_label = font_med.render("Formación: 1-2-2 (GK, DEF+MID, FWD1+FWD2)", True, COL_TEXT_DIM)
        screen.blit(formation_label, ((SCREEN_W - LOG_PANEL_W) // 2 - formation_label.get_width() // 2, SCREEN_H // 2 + 50))

        pygame.display.flip()

        # Handle quit during countdown
        wait_start = pygame.time.get_ticks()
        while pygame.time.get_ticks() - wait_start < 1000:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_q, pygame.K_ESCAPE):
                    pygame.quit()
                    return
            clock.tick(60)

    last_tick_time = pygame.time.get_ticks()

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                    running = False
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_RIGHT:
                    speed = min(10, speed + 1)
                    tick_interval = 2000 // speed
                elif event.key == pygame.K_LEFT:
                    speed = max(1, speed - 1)
                    tick_interval = 2000 // speed
                elif event.key == pygame.K_c:
                    if event_log.copy_to_clipboard():
                        event_log.add(match.tick, COL_BALL, "📋 Log copiado al clipboard!")
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if hasattr(event_log, '_copy_btn_rect') and event_log._copy_btn_rect.collidepoint(event.pos):
                    if event_log.copy_to_clipboard():
                        event_log.add(match.tick, COL_BALL, "📋 Log copiado al clipboard!")

        # Advance simulation
        now = pygame.time.get_ticks()

        # Always decrement goal_timer (even when paused/finished)
        if match.goal_timer > 0:
            match.goal_timer -= 1

        if not paused and not finished and now - last_tick_time >= tick_interval:
            last_tick_time = now

            if match.tick < max_ticks:
                game_state = match.build_state()

                for player in match.home:
                    if use_llm and player.idx in agents:
                        try:
                            summary = summarize_state(game_state, 0, player.idx, labels[player.idx])
                            response = agents[player.idx](summary)
                            cmds = parse_commands(str(response), 0, player.idx)
                            if cmds:
                                match.apply_cmd(player, cmds[0])
                                continue
                        except:
                            pass
                    cmds = fallbacks[player.idx](game_state, 0, player.idx)
                    if cmds:
                        match.apply_cmd(player, cmds[0])

                match.run_away_ai()
                match.ball.update()
                match.check_possession()
                match.check_goals()
                event_log.log_tick(match)
                match.tick += 1
            else:
                finished = True
                event_log.add(match.tick, COL_TEXT, f"🏁 Fin! {match.score[0]}-{match.score[1]}")

        # RENDER
        screen.fill(COL_BG)
        draw_field(screen)
        draw_ball(screen, match.ball)

        for p in match.away:
            draw_player(screen, font_small, p, False)
        for p in match.home:
            draw_player(screen, font_small, p, True)

        draw_scoreboard(screen, font_big, font_small, match)
        draw_action_panel(screen, font_small, match)
        event_log.draw(screen, font_small)

        if match.goal_timer > 0:
            # Brief goal flash (only during the timer, not permanent)
            alpha = min(180, match.goal_timer * 6)
            overlay = pygame.Surface((SCREEN_W - LOG_PANEL_W, 50), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, alpha))
            screen.blit(overlay, (0, FIELD_Y + FIELD_H // 2 - 25))
            col = COL_HOME if match.goal_event == "HOME" else COL_AWAY
            team = "⚽ ¡GOOOL TU EQUIPO!" if match.goal_event == "HOME" else "⚽ Gol del rival"
            goal_text = font_big.render(team, True, col)
            rect = goal_text.get_rect(center=((SCREEN_W - LOG_PANEL_W)//2, FIELD_Y + FIELD_H//2))
            screen.blit(goal_text, rect)

        # Speed indicator
        speed_text = font_small.render(f"Speed: {speed}x  [←/→]  Space=Pause  Q=Quit", True, COL_TEXT_DIM)
        screen.blit(speed_text, (10, SCREEN_H - 15))

        if paused:
            pause_text = font_big.render("⏸ PAUSA", True, COL_TEXT)
            rect = pause_text.get_rect(center=((SCREEN_W - LOG_PANEL_W)//2, SCREEN_H//2))
            screen.blit(pause_text, rect)

        if finished:
            # Small final banner — not blocking
            banner_h = 60
            banner_y = FIELD_Y + FIELD_H // 2 - banner_h // 2
            overlay = pygame.Surface((SCREEN_W - LOG_PANEL_W, banner_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            screen.blit(overlay, (0, banner_y))

            end_text = font_big.render(f"FINAL: {match.score[0]} - {match.score[1]}", True, COL_TEXT)
            rect = end_text.get_rect(center=((SCREEN_W - LOG_PANEL_W)//2, banner_y + 20))
            screen.blit(end_text, rect)

            if match.score[0] > match.score[1]:
                sub = font_small.render("🏆 ¡TU EQUIPO GANA! — Q para salir", True, COL_HOME)
            elif match.score[1] > match.score[0]:
                sub = font_small.render("Perdiste — ajusta los prompts! Q para salir", True, COL_AWAY)
            else:
                sub = font_small.render("Empate — Q para salir", True, COL_TEXT_DIM)
            sub_rect = sub.get_rect(center=((SCREEN_W - LOG_PANEL_W)//2, banner_y + 44))
            screen.blit(sub, sub_rect)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
