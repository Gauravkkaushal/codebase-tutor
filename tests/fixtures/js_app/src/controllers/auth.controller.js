const bcrypt = require('bcrypt');
const User = require('../models/user');
const { signToken } = require('../services/token');

async function login(req, res) {
  const { email, password } = req.body;
  if (!email || !password) {
    return res.status(400).json({ message: 'Missing credentials' });
  }
  const user = await User.findByEmail(email);
  if (!user) {
    return res.status(401).json({ message: 'Invalid credentials' });
  }
  const isMatch = await bcrypt.compare(password, user.password);
  if (!isMatch) {
    return res.status(401).json({ message: 'Invalid credentials' });
  }
  const token = signToken(user);
  return res.json({ token });
}

function logout(req, res) {
  res.status(204).end();
}

module.exports = { login, logout };
