from flask import Flask, render_template, request, redirect, url_for, session
from flask_session import Session
from database import connector, check_login, register_user, get_user_data, init_rooms, update_user, store, get
from process import process
import sqlite3
import os
import random
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecretkey123455'
app.config['SESSION_TYPE'] = 'filesystem'

connector()
rooms = init_rooms()


# ── Tester override commands ──────────────────────────────────────────────────

def handle_override(command):
    username = session['user']
    level    = session['level']
    score    = session['score']
    inventory = session['inventory']

    if command == '**back':
        new_level = max(1, level - 1)
        session['level']         = new_level
        session['objects']       = dict(rooms[new_level].objects)
        session['room_type']     = rooms[new_level].type
        session['door_status']   = 'locked'
        session['sequence_step'] = 0
        session['wrong_attempts'] = 0
        session['log_slid']      = False
        session['key_on_log']    = False
        session['key_lost']      = False
        store(username, score, new_level, inventory, dict(rooms[new_level].objects))
        update_user(username, inventory, new_level, score)
        return f"[OVERRIDE] Level {new_level}: {rooms[new_level].name}"

    if command.startswith('**remove '):
        item_name = command[9:].strip().lower()
        found = next((i for i in inventory if item_name in i.lower()), None)
        if found:
            inventory.remove(found)
            session['inventory'] = inventory
            store(username, score, level, inventory, session['objects'])
            update_user(username, inventory, level, score)
            return f"[OVERRIDE] Removed '{found}' from inventory."
        return f"[OVERRIDE] '{item_name}' not found in inventory."

    return f"[OVERRIDE] Unknown command: {command}"


# ── Home (main game loop) ─────────────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
def home():
    if 'user' not in session:
        return redirect(url_for('login'))

    username, score, level, inventory, objects, door_status = get()
    room_data = rooms[level]
    rtype = session.get('room_type', room_data.type)
    msg = room_data.description

    # Generate a unique end code once when the player reaches level 20
    if level == 20 and 'end_code' not in session:
        now = datetime.now()
        rand = random.randint(10, 99)
        session['end_code'] = (
            f"{username.upper()[:6]}-{now.strftime('%d%m')}-{now.strftime('%H%M')}-{rand}"
        )
    end_code = session.get('end_code', '')

    if request.method == 'POST':
        session['new'] = False
        command = request.form.get('command', '')
        if command.startswith('**'):
            msg = handle_override(command.strip())
        else:
            msg = process(command, inventory, room_data, level, objects)
            if msg == "You exit the room.":
                if level >= 20:
                    return redirect(url_for('win'))
                return redirect(url_for('next_level'))

        # Re-read session — overrides may have changed the level
        username, score, level, inventory, objects, door_status = get()
        room_data = rooms[level]
        rtype = session.get('room_type', room_data.type)

    return render_template(
        'home.html',
        msg=msg, inventory=inventory, user_level=level,
        room_data=room_data, username=username, rtype=rtype, score=score,
        end_code=end_code
    )


# ── Level transition ──────────────────────────────────────────────────────────

@app.route('/next_level', methods=['GET', 'POST'])
def next_level():
    if 'user' not in session:
        return redirect(url_for('login'))

    username = session['user']
    level = session['level']
    inventory = session['inventory']
    score = session['score']

    if request.method == 'POST':
        level += 1
        score += 100
        objects = rooms[level].objects
        store(username, score, level, inventory, objects)
        update_user(username, inventory, level, score)
        session['room_type'] = rooms[level].type
        session['door_status'] = "locked"
        session['sequence_step'] = 0
        session['wrong_attempts'] = 0
        session['log_slid']      = False
        session['key_on_log']    = False
        session['key_lost']      = False
        return redirect(url_for('home'))

    return render_template('next_level.html', user_level=level + 1, username=username)


# ── Win screen ────────────────────────────────────────────────────────────────

@app.route('/win')
def win():
    if 'user' not in session:
        return redirect(url_for('login'))
    username = session['user']
    score = session['score']
    return render_template('win.html', username=username, score=score)


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    msg = ""
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        if check_login(username, password):
            msg = 'Username already exists'
            return render_template('register.html', msg=msg)
        register_user(name, email, username, password, 1, 100, "")
        return redirect(url_for('login'))
    return render_template('register.html', msg=msg)


@app.route('/login', methods=['GET', 'POST'])
def login():
    msg = ""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if check_login(username, password):
            row = get_user_data(username)[0]
            level = row[4]
            score = row[5]
            inventory = row[6].split(",") if row[6] else []
            session['user'] = username
            session['level'] = level
            session['score'] = score
            session['inventory'] = inventory
            session['objects'] = rooms[level].objects
            session['door_status'] = "locked"
            session['room_type'] = rooms[level].type
            session['sequence_step'] = 0
            session['wrong_attempts'] = 0
            session['log_slid']      = False
            session['key_on_log']    = False
            session['key_lost']      = False
            session.pop('end_code', None)
            session['new'] = True
            return redirect(url_for('home'))
        msg = "Invalid username or password."
    return render_template('login.html', msg=msg)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Admin dashboard ───────────────────────────────────────────────────────────

@app.route('/admin')
def admin():
    if 'user' not in session or session['user'] != 'admin':
        return redirect(url_for('home'))
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT name, email, username, level, score, inventory FROM users WHERE username != 'admin' ORDER BY level DESC, score DESC")
    rows = c.fetchall()
    conn.close()

    players = []
    level_counts = [0] * 21
    for row in rows:
        name, email, username, level, score, inventory = row
        items = [i for i in inventory.split(',') if i] if inventory else []
        players.append({
            'name':      name,
            'email':     email,
            'username':  username,
            'level':     level,
            'room_name': rooms[level].name if level <= 20 else 'Done',
            'score':     score,
            'inventory': items,
        })
        if level <= 20:
            level_counts[level] += 1

    stats = {
        'total':     len(players),
        'avg_level': round(sum(p['level'] for p in players) / len(players), 1) if players else 0,
        'finished':  sum(1 for p in players if p['level'] == 20),
        'level_counts': level_counts,
    }
    return render_template('admin.html', players=players, stats=stats, rooms=rooms)


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True)
