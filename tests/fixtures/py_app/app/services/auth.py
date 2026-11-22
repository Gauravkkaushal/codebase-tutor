import os

SECRET = os.environ.get("APP_SECRET")


def check_password(password, stored):
    return password == stored


def login_user(email, password):
    if not email:
        raise ValueError("email required")
    ok = check_password(password, "x")
    return {"ok": ok}


class Session:
    def __init__(self, user):
        self.user = user

    def refresh(self):
        return self.validate()

    def validate(self):
        return self.user is not None
