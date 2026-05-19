from database import get, store, update_user
from flask import session
import re

ITEM_DESCRIPTIONS = {
    "water bottle":     "Your crew water bottle. Dented from years of use. The batch number stamped on the bottom reads: 7.",
    "magnetic keycard": "A standard-issue magnetic keycard. Stamped 'ZONE 3 ACCESS'. There's a coffee stain on the back and someone has drawn a smiley face in marker.",
    "wrench":           "A heavy-duty wrench, slightly rusty. Someone has scratched the initials 'K.D.' into the handle. You wonder who K.D. was.",
    "pipe section":     "A short steel pipe, about 30cm long. Cold to the touch. Smells faintly of coolant.",
    "fitted pipe":      "A pipe section with a coupling tightened onto one end. Solid. Still smells of coolant.",
    "cipher wheel":     "A rotating cipher wheel. Outer ring: letters. Inner ring: numbers. Made by someone with very steady hands.",
    "captain's log":    "The text is encoded — you can't make sense of it as is. You'll need something to decipher it.",
    "decoded log":      "The captain's log, decoded. Most entries are routine. One line stands out: 'If found, use my log on the terminal — it holds command authorisation.'",
    "fuel rod":           "A reactor fuel rod pulsing with dangerous energy. Extremely hot — do not touch with bare hands.",
    "containment sleeve": "A heat-resistant sleeve for handling fuel rods. Rated to 1400°C. The label says 'DO NOT MICROWAVE'.",
    "gloves":             "Heavy-duty heat-resistant gloves. Rated for reactor work. These will protect your hands.",
    "multi-tool":         "A multi-tool. Three of its attachments are missing — but the coupling driver still works.",
    "contained fuel rod": "A fuel rod safely inside its containment sleeve. Ready to insert. Still slightly terrifying.",
    "electromagnet":    "A chunky electromagnet, dead without power. Someone has taped a sticky note to it that reads 'DO NOT USE ON WATCHES'.",
    "power cable":      "A thick two-metre power cable. Slightly frayed at one end. Probably fine.",
    "powered electromagnet": "The electromagnet humming with current. It's already pulled a button off your sleeve.",
    "launch key":       "A solid metal key stamped 'ESCAPE POD LAUNCH — AUTHORISED PERSONNEL ONLY'. Your hands are shaking.",
    "access card":      "Dr. Yara Patel's security access card. Her photo shows someone who did not sleep enough. Relatable.",
    "authorized key":   "The launch key paired with Dr. Patel's access card. The system should accept this. Should.",
}


def process(inp, inventory, room_data, level, objects):
    score = session['score'] - 1
    session['score'] = score
    username = session['user']
    update_user(username, inventory, level, score)

    inp = inp.lower().strip()
    inp = inp.replace('cypher', 'cipher')   # normalise spelling variant
    # Single-letter shortcuts
    shortcuts = {'l': 'look around', 'i': 'inventory', 'e': 'exit', 'h': 'hint'}
    if inp in shortcuts:
        inp = shortcuts[inp]
    original_inp = inp  # preserve before article stripping (needed for switch 'a')
    inp = inp.replace(' the ', ' ').replace(' a ', ' ').replace(' an ', ' ').strip()

    door_status = session['door_status']
    current_type = session.get('room_type', room_data.type)

    try:
        # ── EXIT ────────────────────────────────────────────────────────────
        if inp in ("exit", "exit room", "leave", "leave room", "open door") or inp.startswith("open door"):
            if door_status == "locked":
                # If player mentions the required item, use it automatically
                req = room_data.required_item.lower()
                if req:
                    req_words = req.split()
                    inv = session['inventory']
                    found_req = next((i for i in inv if all(w in i.lower().split() for w in req_words)), None)
                    if found_req and any(w in inp for w in req_words):
                        session['door_status'] = "unlocked"
                        door_status = "unlocked"
                if door_status == "locked":
                    return "The door is sealed."
            inv = session['inventory']
            missing = [item for item in room_data.must_take if item not in inv]
            if missing:
                return f"You should take the {missing[0]} before leaving."
            return "You exit the room."

        # ── HINT ─────────────────────────────────────────────────────────────
        if inp == "hint":
            hints = room_data.hints
            if not hints:
                return "No hints available for this room."
            if session.get('hint_index', 0) >= 1:
                return "You have already used your one hint for this level."
            hint = hints[0]
            session['hint_index'] = 1
            session['score'] = max(0, session['score'] - 5)
            update_user(username, inventory, level, session['score'])
            return f"HINT (-5pts): {hint}"

        # ── HELP ─────────────────────────────────────────────────────────────
        if inp == "help":
            return "Try: look around | look at <thing> | take <item> | use <item> | combine <item> and <item> | exit"

        # ── READ — treat as look at ──────────────────────────────────────────
        if inp.startswith("read "):
            inp = "look at " + inp[5:]

        # ── LOOK AROUND ──────────────────────────────────────────────────────
        if inp in ("look", "look around", "look room"):
            things = [t.strip() for t in room_data.furniture.split(",")]
            msg = "You see: " + ", ".join(things) + "."
            if current_type == "combo":
                msg += " Some items here might work together — try combining them."
            return msg

        # ── LOOK AT / EXAMINE ────────────────────────────────────────────────
        # Accept both "look at <thing>" and "look <thing>"
        if inp.startswith("look at ") or inp.startswith("examine "):
            thing = inp.replace("look at ", "").replace("examine ", "").strip()
        elif inp.startswith("look "):
            thing = inp[5:].strip()
        else:
            thing = None

        if thing is not None:
            if "door" in thing or "keypad" in thing:
                if door_status != "locked":
                    return "The door is open."
                if room_data.door_look_msg:
                    return room_data.door_look_msg
                if current_type == "code":
                    return "The door is sealed. A numeric keypad is mounted beside it. Type the correct code to unlock."
                if current_type == "riddle":
                    return "The door is sealed. A QWERTY keyboard sits at the center of the door."
                if current_type == "inventory":
                    return "The door is sealed with a magnetic lock. You'll need the right card."
                if current_type == "combo":
                    return "The door is sealed. You'll need to figure something out first."
                if current_type == "sequence":
                    return "The door is sealed. Power needs to be restored."
                if current_type == "retrieval":
                    return "The door is sealed. There is a keyhole — and through it you can just make out a metal key inserted from the other side."
                return "The door is sealed."

            thing_key = thing.replace(" ", "")

            # Search keys first, then values (so "look keypad" finds door: <keypad>)
            for key, val in objects.items():
                if thing_key in key.replace(" ", "") or key.replace(" ", "") in thing_key:
                    if not val:
                        return f"There is nothing notable about the {key}."
                    detail = val.replace("<", "").replace(">", "")
                    if detail.startswith(">>"):
                        return detail[2:].strip()
                    return f"You look at the {key}: {detail}."

            for key, val in objects.items():
                if not val:
                    continue
                clean = val.replace("<", "").replace(">", "").replace(" ", "")
                if not clean:
                    continue
                if thing_key in clean or clean in thing_key:
                    item_name = val.replace("<", "").replace(">", "").strip()
                    if item_name.startswith(">>"):
                        return item_name[2:].strip()
                    desc = ITEM_DESCRIPTIONS.get(item_name.lower())
                    if desc:
                        return f"You look at the {item_name}: {desc}"
                    return f"You look at the {key}: {item_name}."

            inv = session['inventory']
            found = next((i for i in inv if thing_key in i.lower().replace(" ", "") or i.lower().replace(" ", "") in thing_key), None)
            if found:
                desc = ITEM_DESCRIPTIONS.get(found.lower(), "Nothing you haven't seen before.")
                return f"You examine the {found}: {desc}"
            return f"You don't see a {thing} here."

        # ── TAKE / GET ───────────────────────────────────────────────────────
        if inp.startswith(("take ", "get ", "pick up ")):
            item = inp.replace("take ", "").replace("get ", "").replace("pick up ", "").strip()
            item_key = item.replace(" ", "").lower()

            # Search takeable items by value (item name), not description text
            for key, val in objects.items():
                if not val or val.startswith("<"):
                    continue
                if item_key in val.replace(" ", "").lower() or val.replace(" ", "").lower() in item_key:
                    # Check if this item requires something in inventory first
                    for req_item, required in room_data.take_requirements.items():
                        if item_key in req_item.replace(" ", "").lower() or req_item.replace(" ", "").lower() in item_key:
                            if required not in [i.lower() for i in session['inventory']]:
                                return f"You reach for the {val} — it's burning hot! You snatch your hand back. You need some kind of protection."
                    _, sc, lv, inv2, obj2, _ = get()
                    inv2.append(val)
                    obj2[key] = ""
                    store(username, sc, lv, inv2, obj2)
                    return f"You take the {val}."

            # Check untakeable items by key name only (not description text)
            for key, val in objects.items():
                if not val or not val.startswith("<"):
                    continue
                if item_key in key.replace(" ", "").lower() or key.replace(" ", "").lower() in item_key:
                    return f"You can't take the {key}."

            return f"You don't see a {item} here."

        # ── COMBINE ──────────────────────────────────────────────────────────
        def attempt_combine():
            if not room_data.combo_items:
                return None
            combo = [c.lower() for c in room_data.combo_items]
            inv = session['inventory']
            found1 = next((i for i in inv if combo[0] in i.lower()), None)
            found2 = next((i for i in inv if combo[1] in i.lower()), None)
            if not found1:
                return f"You don't have a {combo[0]}."
            if not found2:
                return f"You don't have a {combo[1]}."
            # If this combo requires a specific key (e.g. a cipher number)
            if room_data.combo_key:
                if room_data.combo_key not in inp:
                    if re.search(r'\d+', inp):
                        return room_data.combo_wrong_key_msg or "That's not the right setting."
                    return "You'll need to provide a cipher number to decode this."
            _, sc, lv, inv2, obj2, _ = get()
            inv2 = [i for i in inv2 if i != found1 and i != found2]
            inv2.append(room_data.combo_result)
            store(username, sc, lv, inv2, obj2)
            if room_data.combo_key:
                return f"You set the cipher to {room_data.combo_key} and decode the {found2} — you now have a {room_data.combo_result}."
            return f"You combine the {found1} and the {found2} — you now have a {room_data.combo_result}."

        if "combine" in inp:
            result = attempt_combine()
            return result if result else "Those items don't seem to combine usefully here."

        if current_type == "combo" and room_data.combo_items and \
                room_data.combo_result not in session.get('inventory', []):
            combo_lower = [c.lower() for c in room_data.combo_items]
            # Build flexible keywords from all words in item names
            keywords = [w for c in combo_lower for w in c.split()]
            has_item_ref = any(k in inp for k in keywords)
            if room_data.combo_key:
                if has_item_ref and room_data.combo_key in inp:
                    result = attempt_combine()
                    if result:
                        return result
                elif has_item_ref and re.search(r'\d+', inp):
                    return room_data.combo_wrong_key_msg or "That's not the right setting."
                elif has_item_ref:
                    return "You'll need to provide a cipher number to decode this."
            else:
                # Match if at least one keyword from each item name appears in input
                keywords_per_item = [c.split() for c in combo_lower]
                if all(any(w in inp for w in kws) for kws in keywords_per_item):
                    result = attempt_combine()
                    if result:
                        return result

        # ── RETRIEVAL PUZZLE ─────────────────────────────────────────────────
        if current_type == "retrieval":
            log_slid   = session.get('log_slid',   False)
            key_on_log = session.get('key_on_log', False)
            key_lost   = session.get('key_lost',   False)
            inv        = session['inventory']

            # ── Lost key state ──
            if key_lost:
                if any(w in inp for w in ("restart", "reset", "retry", "again")):
                    session['log_slid']   = False
                    session['key_on_log'] = False
                    session['key_lost']   = False
                    _, sc, lv, inv2, obj2, _ = get()
                    inv2 = [i for i in inv2 if "pencil" not in i.lower()]
                    obj2['cabinet'] = 'pencil'
                    store(username, sc, lv, inv2, obj2)
                    return "You reset the room. The key is back in the keyhole and a fresh pencil is in the cabinet."
                return "The key is on the floor on the other side — completely out of reach. Type 'restart' to reset the room and try again."

            # ── Pull log back (key is resting on log) ──
            if key_on_log:
                if any(w in inp for w in ("pull", "retrieve", "drag", "take", "grab")):
                    _, sc, lv, inv2, obj2, _ = get()
                    inv2.append("metal key")
                    session['key_on_log'] = False
                    store(username, sc, lv, inv2, obj2)
                    return "You pull the decoded log back under the door. The metal key slides in with it. You pick up the key."
                return "The key is resting on the decoded log on the other side. Pull the log back to retrieve it."

            # ── Slide log under door ──
            slide_words = ("slide", "slip", "push", "put", "place", "feed")
            if any(w in inp for w in slide_words) and "log" in inp and "door" in inp:
                found_log = next((i for i in inv if "log" in i.lower()), None)
                if not found_log:
                    return "You don't have anything suitable to slide under the door."
                if log_slid:
                    return "The decoded log is already under the door."
                session['log_slid'] = True
                return "You carefully slide the decoded log under the door, leaving the end sticking out on your side."

            # ── Push pencil into keyhole ──
            push_words = ("push", "poke", "insert", "use", "stick", "jab", "prod")
            if any(w in inp for w in push_words) and "pencil" in inp:
                found_pencil = next((i for i in inv if "pencil" in i.lower()), None)
                if not found_pencil:
                    return "You don't have a pencil."
                _, sc, lv, inv2, obj2, _ = get()
                inv2 = [i for i in inv2 if "pencil" not in i.lower()]
                if log_slid:
                    session['key_on_log'] = True
                    store(username, sc, lv, inv2, obj2)
                    return "You push the pencil into the keyhole. The metal key pops out — and lands right on the decoded log! Now pull the log back to retrieve the key."
                else:
                    session['key_lost'] = True
                    store(username, sc, lv, inv2, obj2)
                    return "You push the pencil into the keyhole. The key pops out — but there's nothing beneath it. It clinks to the floor on the other side, completely out of reach. Type 'restart' to reset the room and try again."

        # ── OPEN <thing> ─────────────────────────────────────────────────────
        if inp.startswith("open "):
            target = inp[5:].strip().replace(" ", "")
            # Door always goes through the standard door check
            if "door" in target:
                if door_status == "locked":
                    if "card" in inp or "key" in inp:
                        return "Use the right card."
                    return "The door is sealed."
                return "You exit the room."
            for key, val in objects.items():
                if target in key.replace(" ", "").lower() or key.replace(" ", "").lower() in target:
                    if not val:
                        return f"The {key} is empty."
                    detail = val.replace("<", "").replace(">", "")
                    return f"The {key} is not locked. You open it: {detail}."
            return f"You don't see a {inp[5:].strip()} to open here."

        # ── USE <item> ───────────────────────────────────────────────────────
        use_verbs = ("use ", "insert ", "place ", "put ", "slot ", "apply ", "install ",
                     "fix ", "repair ", "attach ", "connect ", "fit ")
        if inp.startswith(use_verbs):
            # Strip the verb and any "on/in/into/inside <target>" suffix
            for verb in use_verbs:
                if inp.startswith(verb):
                    item = inp[len(verb):]
                    break
            item = re.split(r'\s+(?:on|in|into|inside|onto)\s+', item)[0].strip()
            inv = session['inventory']
            # Match whole words only to avoid "key" matching "keycard"
            words = item.split()
            found = next(
                (i for i in inv if any(w in i.lower().split() for w in words)),
                None
            )
            if not found:
                return f"You don't have a {item}."
            req = room_data.required_item.lower()
            req_words = req.split()
            primary_match = req and all(w in found.lower().split() for w in req_words)
            alt_match = any(
                all(w in found.lower().split() for w in alt.lower().split())
                for alt in room_data.required_item_alt
            )
            if primary_match or alt_match:
                if room_data.use_effect == "reveal":
                    _, sc, lv, inv2, obj2, _ = get()
                    obj2.update(room_data.use_reveal_updates)
                    inv2 = [i for i in inv2 if i != found]
                    store(username, sc, lv, inv2, obj2)
                    msg = room_data.use_reveal_message or f"You use the {found} — something changes in the room."
                    return msg
                session['door_status'] = "unlocked"
                return f"You use the {found}. A mechanism clicks. The door unseals."
            return f"You're not sure how to use the {found} here."

        # ── SEQUENCE ROOM ────────────────────────────────────────────────────
        if current_type == "sequence":
            seq = room_data.sequence
            step = session.get('sequence_step', 0)
            target = seq[step].split()[-1].lower()  # e.g. "a" or "c"
            action_words = {"switch", "flip", "turn", "put", "press",
                            "toggle", "flick", "activate", "on"}
            words = set(original_inp.split())
            if target in words and words & action_words:
                step += 1
                session['sequence_step'] = step
                if step >= len(seq):
                    session['door_status'] = "unlocked"
                    session['sequence_step'] = 0
                    return "Power routed correctly. The door slides open."
                return "Done. What's next?"
            session['sequence_step'] = 0
            return "Wrong sequence — lockout reset. Start again."

        # ── POD ROOM ─────────────────────────────────────────────────────────
        if current_type == "pod":
            if "pod a" in inp:
                return "Pod A has a hull breach. That would be fatal."
            if "pod b" in inp:
                return "Pod B has no fuel. You'd be stranded."
            if "pod c" in inp or inp == "c":
                session['door_status'] = "unlocked"
                return "Pod C's hatch hisses open. You climb inside."
            return "Which pod? Try 'use pod a', 'use pod b', or 'use pod c'."

        # ── END ROOM ─────────────────────────────────────────────────────────
        if current_type == "end":
            if room_data.expected_output and room_data.expected_output.lower() in inp:
                session['door_status'] = "unlocked"
                return (
                    "Identity confirmed: LYRA-7. Launch sequence initiated. "
                    "Pod C detaches from Lyra Station. Stars fill the viewport. You made it."
                )
            return "The computer waits. Enter your crew ID."

        # ── CODE / RIDDLE ────────────────────────────────────────────────────
        if current_type in ("code", "riddle", "inventory"):
            if room_data.expected_output and room_data.expected_output.lower() in inp:
                session['door_status'] = "unlocked"
                session['wrong_attempts'] = 0
                return "Access granted. The door unseals."
            if room_data.expected_output:
                if room_data.max_attempts > 0:
                    attempts = session.get('wrong_attempts', 0) + 1
                    session['wrong_attempts'] = attempts
                    remaining = room_data.max_attempts - attempts
                    if remaining < 0:
                        return "The panel is locked. You'll need to find another way — or start over."
                    if attempts == 1:
                        return f"Wrong. Warning: this panel locks after {room_data.max_attempts} failed attempts. You have {remaining} attempts remaining."
                    if remaining == 0:
                        return "Too many wrong attempts. The panel has locked. You'll need to find another way — or start over."
                    return f"Wrong. {remaining} attempt{'s' if remaining != 1 else ''} remaining before lockout."
                return "Wrong. Try again."

        # ── FLAVOUR ──────────────────────────────────────────────────────────
        if any(w in inp for w in ("hit", "break", "smash", "kick", "destroy")):
            return "This is a space station. Structural integrity matters. Please don't."
        if any(w in inp for w in ("walk", "run", "jump", "pace")):
            return "You pace the room anxiously, burning precious time."
        if "inventory" in inp or inp == "i":
            inv = session['inventory']
            return ("Inventory: " + ", ".join(inv)) if inv else "Your pockets are empty."

        return "That doesn't seem to do anything useful."

    except Exception:
        return "Something went wrong. Try a different command."
