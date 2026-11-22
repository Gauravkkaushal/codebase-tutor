const jwt = require('jsonwebtoken');

function signToken(user) {
  return jwt.sign({ id: user.id }, process.env.JWT_SECRET);
}

module.exports = { signToken };
