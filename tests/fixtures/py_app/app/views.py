from flask import Blueprint, request

from .services.auth import login_user

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    if not data:
        return {"error": "bad request"}, 400
    return login_user(data["email"], data["password"])
