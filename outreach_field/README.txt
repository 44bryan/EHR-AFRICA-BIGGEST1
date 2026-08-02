=========================================
EHR AFRICA — OUTREACH FIELD APPLICATION
=========================================

WHAT IS THIS?
─────────────
This is the offline outreach module for EHR Africa.
It runs on a laptop in the field — no internet needed.
When you return to the hospital, one command syncs everything.


BEFORE GOING TO THE FIELD
──────────────────────────
1. On Windows: double-click run_field.bat
   On Linux/Mac: run ./run_field.sh in terminal

2. The browser opens to http://localhost:8765
   Default login: field_admin / field123
   (Ask your system administrator for your personal login)

3. Create the outreach activity (if not already created at the hospital)

4. You're ready to go!


IN THE FIELD (no internet needed)
──────────────────────────────────
1. Open the browser to http://localhost:8765
2. Navigate to Outreach → Activities → select your activity
3. Click "Register Patient" to add each patient
4. Click "Examine" to record the eye examination
5. If referral needed, the system auto-generates it
6. Print referral letters as PDF from the browser (Ctrl+P)

All data is saved on the laptop. Nothing is lost if the laptop restarts.


BACK AT THE HOSPITAL
─────────────────────
1. Connect the laptop to the hospital network (LAN/WiFi)
2. Open a terminal/command prompt
3. Run: python outreach_field/sync_to_hospital.py

The script will:
- Connect to the hospital server
- Upload all new patients, examinations, and referrals
- Mark all synced records so they are not re-sent
- Show a summary of what was synced

4. Log in to the hospital EHR and go to Outreach → Sync Dashboard
   to confirm everything arrived.


CONFIGURATION
──────────────
Edit outreach_field/settings_field.py to change:
  FIELD_DEVICE_ID    — unique identifier for this laptop
  FIELD_DEVICE_LABEL — human-readable name (e.g. "Outreach Laptop 2")
  HOSPITAL_SERVER_URL — IP address of the hospital server

Or set environment variables:
  FIELD_DEVICE_ID=OUTREACH-LAPTOP-02 python outreach_field/sync_to_hospital.py


TROUBLESHOOTING
────────────────
Q: "python not found" on Windows
A: Install Python 3.10+ from python.org and tick "Add to PATH"

Q: Sync failed — connection refused
A: Make sure the hospital server is on and you are on the hospital network.
   Ping test: ping 192.168.30.169

Q: Browser shows "localhost refused to connect"
A: The field server is not running. Re-run run_field.bat or run_field.sh


SUPPORT
────────
Contact: System Administrator — admin@ehr-africa.local
=========================================
