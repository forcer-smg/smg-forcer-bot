import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=".hacx")

try:
    from database_hybrid import Database
except ImportError:
    from database import Database

USER_ID = 5202575644

print("Connecting to database...")
db = Database()
print("Connected!")

print(f"Adding user {USER_ID} as admin...")
db.add_admin(USER_ID)

if db.is_admin(USER_ID):
    print(f"SUCCESS! User {USER_ID} is now an admin!")
    print("You can now use /admin in Telegram")
else:
    print("FAILED to add admin")

