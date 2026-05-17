import sqlite3
from flask import session
from werkzeug.security import generate_password_hash, check_password_hash


# ── Database helpers ──────────────────────────────────────────────────────────

def connector():
    conn = sqlite3.connect('database.db')
    conn.execute(
        'CREATE TABLE IF NOT EXISTS users '
        '(name TEXT, email TEXT, username TEXT, password TEXT, '
        'level INTEGER, score INTEGER, inventory TEXT)'
    )
    conn.close()

def check_login(username, password):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    if row is None:
        return False
    return check_password_hash(row[0], password)

def get_user_data(username):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    data = c.fetchall()
    conn.close()
    return data

def register_user(name, email, username, password, level, score, inventory):
    hashed = generate_password_hash(password)
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute(
        "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, email, username, hashed, level, score, inventory)
    )
    conn.commit()
    conn.close()

def update_user(username, inventory, level, score):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute(
        "UPDATE users SET level=?, score=?, inventory=? WHERE username=?",
        (level, score, ",".join(inventory), username)
    )
    conn.commit()
    conn.close()

def get():
    return (
        session['user'], session['score'], session['level'],
        session['inventory'], session['objects'], session['door_status']
    )

def store(username, score, level, inventory, objects):
    session['user'] = username
    session['score'] = score
    session['level'] = level
    session['inventory'] = inventory
    session['objects'] = objects


# ── Room definition ───────────────────────────────────────────────────────────

class Room:
    def __init__(self, level=0, name="", description="", type="code",
                 furniture="", objects=None, expected_output="",
                 required_item="", combo_items=None, combo_result="",
                 sequence=None, must_take=None,
                 combo_key="", combo_wrong_key_msg="",
                 take_requirements=None,
                 use_effect="unlock", use_reveal_updates=None,
                 use_reveal_message="",
                 max_attempts=0):
        self.level = level
        self.name = name
        self.description = description
        self.type = type
        self.furniture = furniture
        self.objects = objects or {}
        self.expected_output = expected_output
        self.required_item = required_item      # item needed to unlock door
        self.combo_items = combo_items or []    # [item1, item2] to combine
        self.combo_result = combo_result        # result item name
        self.sequence = sequence or []          # ordered commands for sequence rooms
        self.must_take = must_take or []        # items player must carry before exiting
        self.combo_key = combo_key              # extra keyword required to combine (e.g. "13")
        self.combo_wrong_key_msg = combo_wrong_key_msg  # shown when wrong key used
        self.take_requirements = take_requirements or {}  # {item: required_inventory_item}
        self.use_effect = use_effect or "unlock"          # "unlock" or "reveal"
        self.use_reveal_updates = use_reveal_updates or {}  # objects to update after reveal
        self.use_reveal_message = use_reveal_message       # custom message shown after reveal
        self.max_attempts = max_attempts                   # 0 = no lockout


# ── The Lyra Station Incident — 20 rooms ──────────────────────────────────────

def init_rooms():
    rooms = [None] * 21  # index 0 unused; levels are 1-indexed

    rooms[1] = Room(
        level=1, name="Crew Quarters", type="code",
        description=(
            "Emergency lights flicker red. Your crew ID LYRA-7 is stencilled above your bunk. "
            "Bunk number: 2. There is a bunk, a desk, a storage locker, and a sealed door with a keypad."
        ),
        furniture="bunk,desk,locker,door",
        objects={
            "bunk":   "<pillow — tag reads '4'>",
            "desk":   "<sticky note: PIN = locker batch, then pillow tag, then bunk number>",
            "locker": "<water bottle — batch number '7'>",
            "door":   "<keypad>",
        },
        expected_output="742",
    )

    rooms[2] = Room(
        level=2, name="Storage Corridor", type="inventory",
        description=(
            "A long corridor lined with metal shelving. Emergency rations and equipment are stacked around. "
            "A sealed magnetic door blocks the way forward."
        ),
        furniture="shelf,locker,door",
        objects={
            "shelf":  "magnetic keycard",
            "locker": "<empty>",
            "door":   "<magnetic lock>",
        },
        required_item="magnetic keycard",
    )

    rooms[3] = Room(
        level=3, name="Airlock Antechamber", type="riddle",
        description=(
            "A small chamber before the airlock. A sign on the wall reads: "
            "'I travel fastest of all, have no mass, and fill this room right now. Speak my name to pass.'"
        ),
        furniture="sign,door",
        objects={
            "sign": "<I travel fastest of all, have no mass, and fill this room right now>",
            "door": "<voice-lock panel>",
        },
        expected_output="light",
    )

    rooms[4] = Room(
        level=4, name="Maintenance Bay", type="code",
        description=(
            "Pipes and conduits line every wall. Four pressure gauges are mounted in a row. "
            "A toolbox sits in the corner. A sticky note is pinned nearby."
        ),
        furniture="gauges,toolbox,note,door,keypad",
        objects={
            "gauges":  "<readings left to right: 3, 1, 4, 1>",
            "toolbox": "wrench",
            "note":    "<override code = gauge readings left to right>",
            "door":    "<sealed door>",
            "keypad":  "<numeric keypad beside the door — type the correct code to unlock>",
        },
        expected_output="3141",
        must_take=["wrench"],
    )

    rooms[5] = Room(
        level=5, name="Coolant Control", type="combo",
        description=(
            "A coolant distribution room. A sealed panel blocks access to the door controls. "
            "A pipe section lies on the floor. You carried a wrench from the maintenance bay."
        ),
        furniture="panel,pipe section,door",
        objects={
            "panel":        "<sealed with a corroded bolt — needs a wrench and a pipe>",
            "pipe section": "pipe section",
            "door":         "<coolant reroute required>",
        },
        combo_items=["wrench", "pipe section"],
        combo_result="fitted pipe",
        required_item="fitted pipe",
    )

    rooms[6] = Room(
        level=6, name="Power Relay", type="sequence",
        description=(
            "Banks of switches fill the room. A scorched diagram shows the correct routing. "
            "Three switches are labelled A, B, C. The door needs power restored. Wrong sequence triggers lockout."
        ),
        furniture="switches,diagram,door",
        objects={
            "diagram":  "<power must flow: A then C — do not route through B>",
            "switches": "<three switches labelled A, B, C>",
            "door":     "<no power>",
        },
        sequence=["switch a", "switch c"],
    )

    rooms[7] = Room(
        level=7, name="Hydroponics Lab", type="code",
        description=(
            "Rows of plants grow under artificial light — somehow still alive. "
            "Element labels mark each tray. A research terminal glows nearby."
        ),
        furniture="plants,terminal,note,door",
        objects={
            "plants":   "<trays labelled by element symbol: C, H, N, O>",
            "terminal": "<atomic numbers: C=6, H=1, N=7, O=8>",
            "note":     "<growth formula code: C then H then N then O>",
            "door":     "<keypad>",
        },
        expected_output="6178",
    )

    rooms[8] = Room(
        level=8, name="Communications Array", type="riddle",
        description=(
            "Radio equipment covers the walls. A star chart is pinned above the console. "
            "The console reads: 'Speak the name they spell.'"
        ),
        furniture="console,star chart,door",
        objects={
            "star chart": "<a chart of the night sky — some stars appear to be marked>",
            "console":    "<speak the name they spell>",
            "door":       "<voice panel>",
        },
        expected_output="nova",
    )

    rooms[9] = Room(
        level=9, name="Captain's Quarters", type="combo",
        description=(
            "The captain's private quarters. A cipher wheel hangs on the wall. "
            "An encoded log sits on the desk. The door terminal requires command authorisation."
        ),
        furniture="wall,desk,terminal,door",
        objects={
            "wall":     "cipher wheel",
            "desk":     "captain's log",
            "terminal": "<requires decoded command authorisation>",
            "door":     "<terminal controlled>",
        },
        combo_items=["cipher wheel", "captain's log"],
        combo_result="decoded log",
        required_item="decoded log",
        combo_key="13",
        combo_wrong_key_msg="You are using the wrong number for the cypher.",
    )

    rooms[10] = Room(
        level=10, name="Security Office", type="riddle",
        description=(
            "Crew profiles line the walls. Three names are listed. "
            "The door keypad reads: enter the name of the remaining officer."
        ),
        furniture="profiles,note,door",
        objects={
            "profiles": "<crew manifest: Kai | Dex | Zara>",
            "note":     "<pinned to the board: Kai and Dex have been assigned to their stations>",
            "door":     "<keypad: enter the name of the remaining officer>",
        },
        expected_output="zara",
    )

    rooms[11] = Room(
        level=11, name="Reactor Anteroom", type="code",
        description=(
            "Warning lights cycle on a panel mounted to the wall. "
            "A legend below explains each colour's value. "
            "The door panel reads: ENTER SEQUENCE IN REVERSE."
        ),
        furniture="warning panel,legend,door",
        objects={
            "legend":        "<Red=1, Yellow=3, Green=2, Blue=4>",
            "warning panel": "<current sequence: Yellow, Red, Green, Blue, Red, Yellow>",
            "door":          "<keypad — ENTER SEQUENCE IN REVERSE>",
        },
        expected_output="314213",
    )

    rooms[12] = Room(
        level=12, name="Reactor Core", type="combo",
        description=(
            "The reactor hums dangerously. The fuel rod slot is empty. "
            "A fuel rod glows behind a safety panel. Various equipment is scattered around the room."
        ),
        furniture="reactor,safety panel,cabinet,floor,toolbox,data pad,fire extinguisher,door",
        objects={
            "safety panel":     "fuel rod",
            "cabinet":          "gloves",
            "floor":            "containment sleeve",
            "toolbox":          "multi-tool",
            "data pad":         "<maintenance log: reactor service overdue since 2387.03.12 — all systems critical>",
            "fire extinguisher":"<wall-mounted fire extinguisher — do not remove>",
            "reactor":          "<empty fuel slot — reactor offline>",
            "door":             "<no power — reactor must be fuelled>",
        },
        combo_items=["containment sleeve", "fuel rod"],
        combo_result="contained fuel rod",
        required_item="contained fuel rod",
        take_requirements={"fuel rod": "gloves"},
    )

    rooms[13] = Room(
        level=13, name="Life Support", type="riddle",
        description=(
            "CO2 scrubbers are failing. The override panel displays a message: "
            "'I have seas but no water, mountains but no stone, and cities but no buildings. "
            "Speak my name to restore life support.'"
        ),
        furniture="scrubbers,panel,door",
        objects={
            "scrubbers": "<failing — CO2 levels rising>",
            "panel":     "<I have seas but no water, mountains but no stone, cities but no buildings>",
            "door":      "<voice panel>",
        },
        expected_output="map",
    )

    rooms[14] = Room(
        level=14, name="Navigation Bay", type="code",
        description=(
            "Star charts cover every surface. Three constellations are highlighted with star counts noted. "
            "A nav note explains the dock bay code."
        ),
        furniture="charts,nav note,door",
        objects={
            "charts":   "<three constellation charts — Orion, Lyra and Cygnus — each with stars connected by lines>",
            "nav note": "<dock bay code: Orion — Lyra — Cygnus — Σ>",
            "door":     "<keypad>",
        },
        expected_output="84921",
    )

    rooms[15] = Room(
        level=15, name="Cargo Hold", type="code",
        description=(
            "A vast cargo hold packed with crates. A magnetic crane hangs from the ceiling, "
            "its control panel locked. The exit is completely blocked by stacked cargo."
        ),
        furniture="crane panel,manifest,classification key,crates,door",
        objects={
            "crane panel":         "<magnetic crane — LOCKED. Override code = combined mass of all HZM units in kg>",
            "manifest":            "<CARGO MANIFEST: ELEC 240kg CLR | COOL 165kg HZM | PROV 90kg CLR | FCELL 278kg HZM | MECH 150kg CLR>",
            "classification key":  "<cargo classification codes: CLR = Cleared for transit | HZM = Hazardous Material>",
            "crates":              "<five crates stacked against the exit — they won't budge without the crane>",
            "door":                "<blocked by cargo>",
        },
        expected_output="443",
    )

    rooms[16] = Room(
        level=16, name="Fuel Bay", type="code",
        description=(
            "Fuel storage tanks line the walls. A pressure display shows a sequence "
            "that must be completed to unlock the release valve: B, C, E, H, M, ?"
        ),
        furniture="tanks,display,door",
        objects={
            "display": "<sequence: B, C, E, H, M, ? — enter the next letter>",
            "door":    "<release valve locked>",
        },
        expected_output="u",
        max_attempts=5,
    )

    rooms[17] = Room(
        level=17, name="Escape Pod Prep Bay", type="code",
        description=(
            "Supply storage for the escape pods. Three supply crates are stencilled with pack numbers and weights. "
            "A storage locker is sealed shut — a damaged coupling is leaking pressure and preventing it from opening."
        ),
        furniture="crates,locker,damaged coupling,emergency protocol,door",
        objects={
            "crates":              "<Oxygen: pack 6, weight 82kg | Rations: pack 4, weight 45kg | Medical: pack 3, weight 31kg>",
            "locker":              "<sealed — damaged coupling preventing access>",
            "damaged coupling":    "<leaking pressure — the locker won't open without repair>",
            "emergency protocol":  "<sealed inside the locker — can't reach it>",
            "door":                "<keypad>",
        },
        expected_output="689",
        required_item="fitted pipe",
        use_effect="reveal",
        use_reveal_updates={
            "locker":             "launch key",
            "damaged coupling":   "",
            "emergency protocol": "<EMERGENCY LOAD PROTOCOL: load heaviest cargo first. DOCK CODE = each crate's pack number multiplied by its load position>",
        },
        use_reveal_message="You fit the pipe onto the damaged coupling. It seals with a hiss. The locker pops open — inside you find a launch key and an emergency protocol document.",
        must_take=["launch key"],
    )

    rooms[18] = Room(
        level=18, name="Systems Override", type="combo",
        description=(
            "A master override terminal controls the final corridor. "
            "It requires an authorised launch key. An access card lies on the desk."
        ),
        furniture="terminal,desk,door",
        objects={
            "terminal": "<requires authorised launch key>",
            "desk":     "access card",
            "door":     "<terminal controlled>",
        },
        combo_items=["launch key", "access card"],
        combo_result="authorized key",
        required_item="authorized key",
    )

    rooms[19] = Room(
        level=19, name="Escape Pod Bay", type="retrieval",
        description=(
            "The escape pod bay. The launch door ahead is locked. "
            "Through a porthole you can see three escape pods waiting beyond."
        ),
        furniture="door,cabinet,pods,computer",
        objects={
            "door":     "<heavy locked door — through the keyhole a metal key is visible, inserted from the other side>",
            "keyhole":  "<a metal key inserted from the other side — if only you could push it out onto something>",
            "cabinet":  "pencil",
            "pods":     "<three escape pods — Pod A, Pod B, Pod C — waiting beyond the locked door>",
            "computer": "<screen reads: Last game played: ASYLUM — straight-jacket room>",
        },
        required_item="metal key",
    )

    rooms[20] = Room(
        level=20, name="Escape", type="end_sequence",
        description=(
            "Pod C detaches from Lyra Station with a shudder. "
            "Through the viewport, the station shrinks into the dark. You made it."
        ),
        furniture="viewport",
        objects={
            "viewport": "<stars, and Lyra Station falling away behind you>",
        },
    )

    return rooms
